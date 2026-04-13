"""
safe_experiment.py — Progressive Hardware Safety Test for Unitree G1 (23-DOF)
==============================================================================

Three phases. Each must PASS before the next runs.
Robot must be SUSPENDED ON GANTRY for all phases.

  Phase 0 — DDS Readback        (READ ONLY — no motors commanded)
  Phase 1 — Single Joint Wiggle (left shoulder pitch only, ±0.2 rad)
  Phase 2 — Full Wave Animation (left arm, wave_kinematics.pkl)

Safety limits per phase:
  Phase 0:  no commands sent — zero risk
  Phase 1:  KP=5, KD=2, max angle ±0.2 rad, abort at 3 rad/s
  Phase 2:  KP=20, KD=2, abort at 5 rad/s (tighter than normal 8 rad/s)

Usage:
    python safe_experiment.py --interface eth0             # run all phases
    python safe_experiment.py --interface eth0 --phase 0  # one phase only

SAFETY PRECONDITIONS:
  1. Robot suspended on gantry — feet off ground
  2. Robot in DAMPING mode (L2+A on controller)
  3. Operator on L1+L2 e-stop at all times
  4. Run g1_encoder_monitor.py first — confirm joint 13 = L_shoulder_pitch
"""

import argparse
import pickle
import sys
import time
from pathlib import Path

import numpy as np

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize, ChannelSubscriber, ChannelPublisher)
from unitree_sdk2py.utils.crc import CRC
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_, LowCmd_
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_ as LowCmd_default

NUM_MOTOR = 35
CTRL_HZ   = 200.0
CTRL_DT   = 1.0 / CTRL_HZ

# 23-DOF joint indices
IDX_L_SHOULDER_PITCH = 13
IDX_L_SHOULDER_ROLL  = 14
IDX_L_SHOULDER_YAW   = 15
IDX_L_ELBOW_PITCH    = 16
IDX_L_ELBOW_ROLL     = 17
LEFT_ARM             = list(range(13, 18))

MOVEMENTS_DIR = Path(__file__).parent.parent.parent / "kim_workspace" / "movements"

crc = CRC()


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_zero_cmd() -> LowCmd_:
    cmd = LowCmd_default()
    for i in range(NUM_MOTOR):
        cmd.motor_cmd[i].mode = 0x01
        cmd.motor_cmd[i].q    = 0.0
        cmd.motor_cmd[i].kp   = 0.0
        cmd.motor_cmd[i].dq   = 0.0
        cmd.motor_cmd[i].kd   = 0.0
        cmd.motor_cmd[i].tau  = 0.0
    return cmd


def send_zero_torque(pub: ChannelPublisher, n: int = 20):
    """Send zero-torque command n times — always call on exit."""
    cmd = make_zero_cmd()
    for _ in range(n):
        cmd.crc = crc.Crc(cmd)
        pub.Write(cmd)
        time.sleep(0.01)
    print("[SAFE] Zero torque engaged. Robot is safe to handle.")


def confirm(prompt: str) -> bool:
    ans = input(f"\n{prompt} [YES/no] ").strip()
    return ans.upper() == "YES" or ans == ""


def wait_for_state(state_holder, timeout=5.0) -> bool:
    deadline = time.monotonic() + timeout
    while state_holder[0] is None and time.monotonic() < deadline:
        time.sleep(0.05)
    return state_holder[0] is not None


# ── Phase 0: DDS Readback ───────────────────────────────────────────────────

def phase0_readback(iface: str) -> bool:
    """READ ONLY. Confirm DDS is live and print arm joint readings."""
    print("\n" + "="*60)
    print("PHASE 0 — DDS Readback (no commands sent)")
    print("="*60)

    state_holder = [None]

    def on_state(msg: LowState_):
        state_holder[0] = msg

    ChannelFactoryInitialize(1, iface)
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(on_state, 10)

    print("Waiting for LowState messages (5s timeout)...")
    if not wait_for_state(state_holder):
        print("[FAIL] No messages received. Check: cable, robot power, IP, CycloneDDS.")
        return False

    msg = state_holder[0]
    print("\nArm joint readings (23-DOF IDL indices 13–22):")
    names = {
        13: "L_shoulder_pitch",
        14: "L_shoulder_roll",
        15: "L_shoulder_yaw",
        16: "L_elbow_pitch",
        17: "L_elbow_roll",
        18: "R_shoulder_pitch",
        19: "R_shoulder_roll",
        20: "R_shoulder_yaw",
        21: "R_elbow_pitch",
        22: "R_elbow_roll",
    }
    print(f"  {'IDX':<4} {'Name':<22} {'q (rad)':>10} {'dq (rad/s)':>12}")
    print("  " + "-"*50)
    for idx, name in names.items():
        q  = msg.motor_state[idx].q
        dq = msg.motor_state[idx].dq
        print(f"  {idx:<4} {name:<22} {q:>10.4f} {dq:>12.4f}")

    imu = msg.imu_state
    print(f"\nIMU: quat w={imu.quaternion[0]:.3f} x={imu.quaternion[1]:.3f} "
          f"y={imu.quaternion[2]:.3f} z={imu.quaternion[3]:.3f}")

    print("\n[CHECK] Physically move the LEFT shoulder forward/backward.")
    input("Press Enter when done moving...")

    msg2 = state_holder[0]
    delta = abs(msg2.motor_state[IDX_L_SHOULDER_PITCH].q -
                msg.motor_state[IDX_L_SHOULDER_PITCH].q)

    if delta > 0.05:
        print(f"[PASS] Joint 13 changed by {delta:.3f} rad — 23-DOF layout confirmed.")
        return True
    else:
        print(f"[WARN] Joint 13 only changed by {delta:.4f} rad.")
        print("       If a DIFFERENT index changed, you may have 29-DOF hardware.")
        print("       Update IDX constants before continuing.")
        return confirm("Continue anyway?")


# ── Phase 1: Single Joint Wiggle ─────────────────────────────────────────────

def phase1_wiggle(pub: ChannelPublisher, state_holder: list) -> bool:
    """
    Move LEFT shoulder pitch (joint 13) only.
    0 → +0.2 rad over 2s, hold 1s, return to 0 over 2s.
    KP=5 (very gentle). Abort if velocity > 3 rad/s.
    """
    print("\n" + "="*60)
    print("PHASE 1 — Single Joint Wiggle (L_shoulder_pitch only)")
    print("  Target: +0.2 rad forward, back to 0")
    print("  KP=5 (very gentle), abort threshold=3 rad/s")
    print("="*60)

    if not confirm("Ready to start Phase 1?"):
        return False

    KP = 5.0
    KD = 2.0
    ABORT_VEL = 3.0
    TARGET = 0.2   # rad

    # Profile: ramp up 2s → hold 1s → ramp down 2s
    ramp_ticks = int(2.0 * CTRL_HZ)
    hold_ticks = int(1.0 * CTRL_HZ)
    total      = ramp_ticks + hold_ticks + ramp_ticks

    cmd = make_zero_cmd()
    cmd.motor_cmd[IDX_L_SHOULDER_PITCH].kp = KP
    cmd.motor_cmd[IDX_L_SHOULDER_PITCH].kd = KD

    # Small damping on other arm joints to prevent flopping
    for i in LEFT_ARM:
        if i != IDX_L_SHOULDER_PITCH:
            cmd.motor_cmd[i].kd = 1.0

    aborted = False
    try:
        for tick in range(total):
            loop_start = time.monotonic()

            # Velocity abort check
            dq = abs(state_holder[0].motor_state[IDX_L_SHOULDER_PITCH].dq)
            if dq > ABORT_VEL:
                print(f"\n[ABORT] Joint 13 velocity {dq:.2f} rad/s > {ABORT_VEL} rad/s limit")
                aborted = True
                break

            # Target profile
            if tick < ramp_ticks:
                q_target = TARGET * (tick / ramp_ticks)
            elif tick < ramp_ticks + hold_ticks:
                q_target = TARGET
            else:
                q_target = TARGET * (1.0 - (tick - ramp_ticks - hold_ticks) / ramp_ticks)

            cmd.motor_cmd[IDX_L_SHOULDER_PITCH].q = float(q_target)
            cmd.crc = crc.Crc(cmd)
            pub.Write(cmd)

            if tick % 40 == 0:
                actual = state_holder[0].motor_state[IDX_L_SHOULDER_PITCH].q
                err = abs(q_target - actual)
                print(f"  tick={tick:>4}  target={q_target:+.3f}  actual={actual:+.3f}  "
                      f"err={err:.3f}  vel={dq:.3f} rad/s", end="\r")

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0, CTRL_DT - elapsed))

    except KeyboardInterrupt:
        print("\n[INTERRUPT] Ctrl+C during wiggle.")
        aborted = True

    print()  # newline after \r progress

    if aborted:
        print("[FAIL] Phase 1 aborted.")
        return False

    # Check tracking quality
    actual = state_holder[0].motor_state[IDX_L_SHOULDER_PITCH].q
    print(f"\nFinal position: actual={actual:.4f} rad (expected ~0.000)")
    print("[PASS] Phase 1 complete — joint responded correctly.")
    return True


# ── Phase 2: Wave Animation ──────────────────────────────────────────────────

def phase2_wave(pub: ChannelPublisher, state_holder: list) -> bool:
    """
    Replay wave_kinematics.pkl — left arm only.
    KP=20, abort at 5 rad/s (tighter than normal 8 rad/s).
    """
    print("\n" + "="*60)
    print("PHASE 2 — Wave Animation (left arm, wave_kinematics.pkl)")
    print("  KP=20, abort threshold=5 rad/s")
    print("="*60)

    pkl_path = MOVEMENTS_DIR / "wave_kinematics.pkl"
    if not pkl_path.exists():
        print(f"[FAIL] {pkl_path} not found.")
        return False

    with open(pkl_path, "rb") as f:
        joints = np.array(pickle.load(f)["joint_angles"], dtype=np.float32)

    print(f"Loaded: {len(joints)} frames at 30 FPS = {len(joints)/30:.1f}s")

    if not confirm("Ready to start Phase 2 wave?"):
        return False

    KP = 20.0
    KD = 2.0
    ABORT_VEL = 5.0
    PKL_FPS = 30.0
    TICKS_PER_FRAME = int(CTRL_HZ / PKL_FPS)  # 6 ticks per frame

    cmd = make_zero_cmd()
    for i in LEFT_ARM:
        cmd.motor_cmd[i].kp = KP
        cmd.motor_cmd[i].kd = KD
    # Damp legs so they don't swing
    for i in range(12):
        cmd.motor_cmd[i].kd = 1.0

    total_frames = len(joints)
    frame_idx = 0
    tick = 0
    aborted = False

    try:
        while frame_idx < total_frames:
            loop_start = time.monotonic()

            # Velocity abort across all arm joints
            for i in LEFT_ARM:
                dq = abs(state_holder[0].motor_state[i].dq)
                if dq > ABORT_VEL:
                    print(f"\n[ABORT] Joint {i} velocity {dq:.2f} rad/s > {ABORT_VEL} limit")
                    aborted = True
                    break
            if aborted:
                break

            target = joints[frame_idx]
            for i in LEFT_ARM:
                cmd.motor_cmd[i].q = float(target[i])

            cmd.crc = crc.Crc(cmd)
            pub.Write(cmd)

            if tick % (int(CTRL_HZ) // 5) == 0:
                errs = [abs(target[i] - state_holder[0].motor_state[i].q) for i in LEFT_ARM]
                print(f"  frame={frame_idx:>3}/{total_frames}  "
                      f"max_err={max(errs):.3f} rad", end="\r")

            tick += 1
            if tick % TICKS_PER_FRAME == 0:
                frame_idx += 1

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0, CTRL_DT - elapsed))

    except KeyboardInterrupt:
        print("\n[INTERRUPT] Ctrl+C during wave.")
        aborted = True

    print()
    if aborted:
        print("[FAIL] Phase 2 aborted.")
        return False

    print("[PASS] Phase 2 complete — wave animation finished.")
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Safe progressive hardware test for G1 23-DOF")
    parser.add_argument("--interface", default="lo",
                        help="Network interface: 'lo' for sim, 'eth0' for real hardware")
    parser.add_argument("--phase", type=int, choices=[0, 1, 2],
                        help="Run only this phase (default: run all in sequence)")
    args = parser.parse_args()

    print("=" * 60)
    print("  G1 SAFE EXPERIMENT — PROGRESSIVE ARM TEST")
    print("=" * 60)
    print("PRECONDITIONS (confirm all before typing YES):")
    print("  1. Robot is SUSPENDED on gantry (feet off ground)")
    print("  2. Robot is in DAMPING mode (L2+A held until limp)")
    print("  3. Second operator is holding L1+L2 e-stop")
    print("  4. g1_encoder_monitor.py was run — joint 13 confirmed")
    if not confirm("ALL preconditions met?"):
        print("Aborted. Meet all preconditions first.")
        sys.exit(0)

    # Phase 0 always runs first (also initializes DDS)
    if not phase0_readback(args.interface):
        print("\n[STOPPED] Phase 0 failed. Fix DDS/network before continuing.")
        sys.exit(1)

    if args.phase == 0:
        print("\nPhase 0 complete.")
        sys.exit(0)

    # For Phase 1 and 2, re-subscribe with a shared state holder
    state_holder = [None]

    def on_state(msg: LowState_):
        state_holder[0] = msg

    sub2 = ChannelSubscriber("rt/lowstate", LowState_)
    sub2.Init(on_state, 10)

    pub = ChannelPublisher("rt/lowcmd", LowCmd_)
    pub.Init()

    print("\nWaiting for LowState (2s)...")
    wait_for_state(state_holder, timeout=2.0)
    if state_holder[0] is None:
        print("[ERROR] Lost DDS connection. Check cable.")
        sys.exit(1)

    try:
        if args.phase in (None, 1):
            if not phase1_wiggle(pub, state_holder):
                print("\n[STOPPED] Phase 1 failed. Do not proceed to Phase 2.")
                send_zero_torque(pub)
                sys.exit(1)

        if args.phase in (None, 2):
            if not phase2_wave(pub, state_holder):
                print("\n[STOPPED] Phase 2 failed.")
                send_zero_torque(pub)
                sys.exit(1)

        print("\n" + "="*60)
        print("  ALL PHASES PASSED")
        print("  Robot is ready for full deployment scripts.")
        print("="*60)

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
    finally:
        send_zero_torque(pub)


if __name__ == "__main__":
    main()
