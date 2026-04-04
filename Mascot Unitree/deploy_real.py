"""
deploy_real.py — Stream a pkl trajectory to a real Unitree G1 (23-DOF) via unitree_sdk2py.

Prerequisites:
  pip install unitree_sdk2py
  Robot connected via Ethernet, IP 192.168.123.x
  Robot in DAMPING mode before running (press L2+A on controller)

Usage:
  python deploy_real.py --pkl output/2026-03-12_07-07-09.pkl --iface eth0
  python deploy_real.py --pkl output/spiderman_webshoot.pkl --iface eth0 --speed 0.5
  python deploy_real.py --pkl ... --dry-run        # print plan, do not move robot

Joint index mapping (pkl ↔ SDK motor index — identical ordering):
  0  left_hip_pitch       15 left_shoulder_pitch
  1  left_hip_roll        16 left_shoulder_roll
  2  left_hip_yaw         17 left_shoulder_yaw
  3  left_knee            18 left_elbow
  4  left_ankle_pitch     19 left_wrist_roll
  5  left_ankle_roll      20 left_wrist_pitch   ← passive in 23-DOF (locked to 0)
  6  right_hip_pitch      21 left_wrist_yaw     ← passive in 23-DOF (locked to 0)
  7  right_hip_roll       22 right_shoulder_pitch
  8  right_hip_yaw        23 right_shoulder_roll
  9  right_knee           24 right_shoulder_yaw
  10 right_ankle_pitch    25 right_elbow
  11 right_ankle_roll     26 right_wrist_roll
  12 waist_yaw            27 right_wrist_pitch  ← passive in 23-DOF (locked to 0)
  13 waist_roll           ← passive in 23-DOF  28 right_wrist_yaw   ← passive in 23-DOF (locked to 0)
  14 waist_pitch          ← passive in 23-DOF
"""

import argparse
import pickle
import sys
import time
import numpy as np

# ── Joint limits (rad) from g1_23dof.xml ────────────────────────────────────
JOINT_LIMITS = np.array([
    [-2.5307,  2.8798],  # 0  left_hip_pitch
    [-0.5236,  2.9671],  # 1  left_hip_roll
    [-2.7576,  2.7576],  # 2  left_hip_yaw
    [-0.0873,  2.8798],  # 3  left_knee
    [-0.8727,  0.5236],  # 4  left_ankle_pitch
    [-0.2618,  0.2618],  # 5  left_ankle_roll
    [-2.5307,  2.8798],  # 6  right_hip_pitch
    [-2.9671,  0.5236],  # 7  right_hip_roll
    [-2.7576,  2.7576],  # 8  right_hip_yaw
    [-0.0873,  2.8798],  # 9  right_knee
    [-0.8727,  0.5236],  # 10 right_ankle_pitch
    [-0.2618,  0.2618],  # 11 right_ankle_roll
    [-2.6180,  2.6180],  # 12 waist_yaw
    [-0.5236,  0.5236],  # 13 waist_roll       (passive, keep 0)
    [-0.5236,  0.5236],  # 14 waist_pitch      (passive, keep 0)
    [-3.0892,  2.6704],  # 15 left_shoulder_pitch
    [-1.5882,  2.2515],  # 16 left_shoulder_roll
    [-2.6180,  2.6180],  # 17 left_shoulder_yaw
    [-1.0472,  2.0944],  # 18 left_elbow
    [-1.9722,  1.9722],  # 19 left_wrist_roll
    [-1.6100,  1.6100],  # 20 left_wrist_pitch  (passive, keep 0)
    [-1.6100,  1.6100],  # 21 left_wrist_yaw    (passive, keep 0)
    [-3.0892,  2.6704],  # 22 right_shoulder_pitch
    [-2.2515,  1.5882],  # 23 right_shoulder_roll
    [-2.6180,  2.6180],  # 24 right_shoulder_yaw
    [-1.0472,  2.0944],  # 25 right_elbow
    [-1.9722,  1.9722],  # 26 right_wrist_roll
    [-1.6100,  1.6100],  # 27 right_wrist_pitch (passive, keep 0)
    [-1.6100,  1.6100],  # 28 right_wrist_yaw   (passive, keep 0)
])

# Passive joints — zero position, near-zero gains, not sent to actuators
PASSIVE_IDX = {13, 14, 20, 21, 27, 28}   # waist_roll/pitch + wrist_pitch/yaw

# PD gains per joint index
KP = np.array([
    150, 150, 150, 200, 50, 50,    # left leg
    150, 150, 150, 200, 50, 50,    # right leg
    100, 0,   0,                   # waist (yaw only; roll/pitch passive → gain 0)
    80,  80,  80,  80,  40,  0,  0,  # left arm (wrist_pitch/yaw passive)
    80,  80,  80,  80,  40,  0,  0,  # right arm
])

KD = np.array([
    5,  5,  5,  5,  2,  2,    # left leg
    5,  5,  5,  5,  2,  2,    # right leg
    3,  0,  0,                 # waist
    2,  2,  2,  2,  1,  0,  0,  # left arm
    2,  2,  2,  2,  1,  0,  0,  # right arm
])

# G1 safe standing pose (zero = default upright for arms, slight knee bend for legs)
STAND_POSE = np.zeros(29)
STAND_POSE[3]  =  1.20   # left_knee
STAND_POSE[4]  = -0.60   # left_ankle_pitch
STAND_POSE[9]  =  1.20   # right_knee
STAND_POSE[10] = -0.60   # right_ankle_pitch
STAND_POSE[1]  =  0.0    # hip_roll neutral
STAND_POSE[7]  =  0.0

# Control loop dt
DT = 0.002   # 500 Hz

NUM_DOF = 29  # SDK motor slots used


def load_trajectory(pkl_path: str) -> tuple[list, float]:
    with open(pkl_path, "rb") as f:
        traj = pickle.load(f)
    dof_pos = np.array(traj["dof_pos"])   # (N, 29)
    fps = float(traj.get("fps", 10.0))
    print(f"  Loaded {len(dof_pos)} frames @ {fps} fps  ({len(dof_pos)/fps:.1f}s)")
    return dof_pos, fps


def clamp_to_limits(q: np.ndarray) -> np.ndarray:
    return np.clip(q, JOINT_LIMITS[:, 0], JOINT_LIMITS[:, 1])


def velocity_limit_filter(q_prev: np.ndarray, q_target: np.ndarray,
                           max_vel: float = 3.0) -> np.ndarray:
    """Clamp joint velocity to max_vel rad/s at DT."""
    dq = q_target - q_prev
    dq_max = max_vel * DT
    dq = np.clip(dq, -dq_max, dq_max)
    return q_prev + dq


def send_cmd(pub, cmd_proto, crc, q: np.ndarray, dq: np.ndarray = None):
    """Write one LowCmd frame."""
    if dq is None:
        dq = np.zeros(NUM_DOF)
    cmd = cmd_proto
    for i in range(NUM_DOF):
        cmd.motor_cmd[i].mode = 0x01     # PMSM servo mode
        cmd.motor_cmd[i].q   = float(q[i])
        cmd.motor_cmd[i].dq  = float(dq[i])
        cmd.motor_cmd[i].kp  = float(KP[i])
        cmd.motor_cmd[i].kd  = float(KD[i])
        cmd.motor_cmd[i].tau = 0.0
    cmd.crc = crc.Crc(cmd)
    pub.Write(cmd)


def phase_interp(q_from: np.ndarray, q_to: np.ndarray,
                 duration: float, pub, cmd_proto, crc):
    """Smoothly move from q_from → q_to over duration seconds."""
    steps = int(duration / DT)
    for step in range(steps):
        t = step / max(steps - 1, 1)
        s = 0.5 - 0.5 * np.cos(np.pi * t)   # smooth cosine ramp
        q = (1 - s) * q_from + s * q_to
        q = clamp_to_limits(q)
        send_cmd(pub, cmd_proto, crc, q)
        time.sleep(DT)


def dry_run_summary(dof_pos: np.ndarray, fps: float, speed: float):
    n = len(dof_pos)
    dur = n / fps / speed
    print(f"\n{'='*55}")
    print(f"  DRY RUN — no robot motion")
    print(f"  Frames    : {n}")
    print(f"  Source fps : {fps:.1f}")
    print(f"  Speed      : {speed:.2f}x  →  playback {n/fps:.1f}s / {dur:.1f}s wall")
    print(f"  DOF range  :")
    for i in range(29):
        lo, hi = dof_pos[:, i].min(), dof_pos[:, i].max()
        limit_ok = lo >= JOINT_LIMITS[i, 0] and hi <= JOINT_LIMITS[i, 1]
        flag = "" if limit_ok else "  ⚠️  EXCEEDS LIMIT"
        print(f"    [{i:2d}]  {lo:+.3f} .. {hi:+.3f}{flag}")
    print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Deploy G1 trajectory to real robot")
    parser.add_argument("--pkl",   required=True, help="Path to robot_motion.pkl")
    parser.add_argument("--iface", default="eth0",
                        help="Network interface (e.g. eth0, en0)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Playback speed multiplier (default 1.0)")
    parser.add_argument("--standup-time", type=float, default=5.0,
                        help="Seconds to ease into standing pose before playback")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan and limit check only — do not move robot")
    parser.add_argument("--smooth", type=float, default=0.3,
                        help="EMA smoothing alpha 0–1 (0=none, 1=freeze). Default 0.3")
    args = parser.parse_args()

    dof_pos, fps = load_trajectory(args.pkl)

    if args.dry_run:
        dry_run_summary(dof_pos, fps, args.speed)
        return

    # ── Import SDK (only needed for real run) ──────────────────────────────
    try:
        from unitree_sdk2py.core.channel import (
            ChannelFactoryInitialize, ChannelPublisher, ChannelSubscriber,
        )
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
        from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_ as LowCmd_default
        from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowState_ as LowState_default
        from unitree_sdk2py.utils.crc import CRC
    except ImportError:
        print("unitree_sdk2py not installed.  pip install unitree_sdk2py")
        sys.exit(1)

    # ── Safety confirmation ────────────────────────────────────────────────
    print("\n" + "!"*55)
    print("  REAL ROBOT DEPLOYMENT")
    print(f"  PKL    : {args.pkl}")
    print(f"  Iface  : {args.iface}")
    print(f"  Speed  : {args.speed}x")
    print(f"  Frames : {len(dof_pos)}  ({len(dof_pos)/fps:.1f}s of motion)")
    print("!"*55)
    print("\nChecklist before proceeding:")
    print("  ✓ Robot is powered on and in DAMPING mode (L2+A)")
    print("  ✓ Robot is standing on a flat surface with clear 1m radius")
    print("  ✓ E-stop (L1+L2) ready on controller")
    print("  ✓ Ethernet connected to", args.iface)
    ans = input("\nType 'go' to start, anything else to abort: ").strip().lower()
    if ans != "go":
        print("Aborted.")
        return

    # ── Connect ────────────────────────────────────────────────────────────
    ChannelFactoryInitialize(0, args.iface)
    pub = ChannelPublisher("rt/lowcmd", LowCmd_)
    pub.Init()

    # Subscribe to LowState to read current joint positions
    current_q = np.zeros(NUM_DOF)
    _got_state = [False]

    def _low_state_cb(msg: LowState_):
        for i in range(NUM_DOF):
            current_q[i] = msg.motor_state[i].q
        _got_state[0] = True

    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(_low_state_cb, 10)

    cmd_proto = LowCmd_default()
    cmd_proto.head[0] = 0xFE
    cmd_proto.head[1] = 0xEF
    crc = CRC()

    print("Waiting for robot state...", end="", flush=True)
    for _ in range(500):
        if _got_state[0]:
            break
        time.sleep(0.01)
    if not _got_state[0]:
        print("\n⛔ No LowState received — check connection.")
        return
    print(" OK")
    print(f"  Current q[0] (left_hip_pitch) = {current_q[0]:.4f} rad")

    # ── Phase 1: ease to standing pose ───────────────────────────────────
    print(f"\n[1/3] Easing to stand pose over {args.standup_time:.1f}s ...")
    q_start = current_q.copy()
    phase_interp(q_start, STAND_POSE, args.standup_time, pub, cmd_proto, crc)
    print("  Stand pose reached.")
    time.sleep(1.0)

    # ── Phase 2: ease to first pkl frame ─────────────────────────────────
    first_frame = clamp_to_limits(np.array(dof_pos[0]))
    print("[2/3] Easing to first motion frame (3s) ...")
    phase_interp(STAND_POSE, first_frame, 3.0, pub, cmd_proto, crc)
    print("  Ready. Starting playback in 1s ...")
    time.sleep(1.0)

    # ── Phase 3: trajectory playback ─────────────────────────────────────
    frame_dt = 1.0 / (fps * args.speed)   # wall-clock time per pkl frame
    steps_per_frame = max(1, int(frame_dt / DT))
    n_frames = len(dof_pos)
    print(f"[3/3] Playing {n_frames} frames at {fps*args.speed:.1f} fps "
          f"({n_frames/fps/args.speed:.1f}s) — Ctrl+C to stop")

    q_current = first_frame.copy()
    q_smoothed = first_frame.copy()   # EMA state — tracks smoothed command
    smooth_alpha = float(np.clip(args.smooth, 0.0, 1.0))
    if smooth_alpha > 0:
        print(f"  EMA smoothing enabled  alpha={smooth_alpha:.2f}  "
              f"(higher = more smoothing, 0 = off)")
    try:
        for fi in range(n_frames - 1):
            q_a = clamp_to_limits(np.array(dof_pos[fi]))
            q_b = clamp_to_limits(np.array(dof_pos[fi + 1]))
            t_frame = time.perf_counter()

            for step in range(steps_per_frame):
                t = step / steps_per_frame
                q_target = (1 - t) * q_a + t * q_b
                # Velocity-limit filter — caps joint speed at 3 rad/s
                q_current = velocity_limit_filter(q_current, q_target)
                # EMA smoother (TWIST2-style) — reduces jerky commands that destabilize the robot.
                # q_smoothed lags behind q_current; alpha=0 disables, alpha→1 freezes output.
                q_smoothed = smooth_alpha * q_smoothed + (1.0 - smooth_alpha) * q_current
                # Hard clip to joint limits (final safety gate before hardware)
                q_out = clamp_to_limits(q_smoothed)
                send_cmd(pub, cmd_proto, crc, q_out)
                elapsed = time.perf_counter() - t_frame
                wait = (step + 1) * DT - elapsed
                if wait > 0:
                    time.sleep(wait)

            if fi % 10 == 0:
                pct = int(100 * fi / n_frames)
                print(f"  Frame {fi:4d}/{n_frames}  [{pct:3d}%]", end="\r")

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user.")

    # ── Phase 4: return to stand ──────────────────────────────────────────
    print("\n[4/4] Returning to stand pose (3s) ...")
    phase_interp(q_smoothed, STAND_POSE, 3.0, pub, cmd_proto, crc)
    print("✅ Done. Robot is in stand pose. Switch to SPORT mode to resume normal operation.")


if __name__ == "__main__":
    main()
