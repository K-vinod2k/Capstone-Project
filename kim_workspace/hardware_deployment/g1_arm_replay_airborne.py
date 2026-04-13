"""
G1 Arm Replay — Airborne Low-Gain Kinematic Replay (Step 4)
------------------------------------------------------------
SAFETY PRECONDITIONS (do not skip):
  1. Robot is SUSPENDED on gantry — feet off the ground
  2. g1_encoder_monitor.py was run and joint indices confirmed 1:1
  3. Robot was booted in DAMPING mode, then taken to zero-torque manually
  4. An operator is ready on the L1+L2 emergency stop

What this script does:
  - Loads hulk_kinematics.pkl (35-DOF, 100 frames at 30 FPS)
  - Leg joints (0-11) and waist (12-14): kp=0, kd=2.0 — soft damping only
  - Arm joints (15-28): kp=20, kd=2.0 — loose position tracking
  - Extended joints (29-34): kp=0, kd=0 — zero torque (unknown mapping)
  - Replays a SINGLE arm (left arm, joints 15-21) on first run
  - Aborts if any joint velocity exceeds VELOCITY_ABORT_THRESHOLD

Kp=20 is ~10% of simulation Kp=200. The arm will track loosely.
This is intentional — we are validating the retargeting layer, not achieving
precise control. If the arm oscillates or diverges, stop and diagnose.

Usage:
    python g1_arm_replay_airborne.py --pkl ../../vinod_workspace/hulk_kinematics.pkl
    python g1_arm_replay_airborne.py --pkl ../../vinod_workspace/hulk_kinematics.pkl --both-arms
    python g1_arm_replay_airborne.py --pkl ../../vinod_workspace/hulk_kinematics.pkl --interface eth0

ASSUMPTION TO FALSIFY:
    GMR retargeting joint ordering matches hardware IDL motor indices 0-34.
    Confirm by running g1_encoder_monitor.py first and manually checking
    that pkl joint 15 (L_shoulder_pitch) moves the correct physical joint.
"""

import sys
import time
import pickle
import argparse
import numpy as np

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber, ChannelPublisher
from unitree_sdk2py.utils.crc import CRC
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_, LowCmd_
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_ as LowCmd_default
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowState_ as LowState_default

NUM_MOTOR = 35

# Joint index ranges — 23-DOF hardware IDL
LEG_JOINTS   = list(range(0, 12))    # 0-11:  both legs
WAIST_JOINTS = [12]                  # 12: TORSO (waist_yaw only on 23-DOF)
LEFT_ARM     = list(range(13, 18))   # 13-17: L_shoulder x3, L_elbow x2
RIGHT_ARM    = list(range(18, 23))   # 18-22: R_shoulder x3, R_elbow x2
EXT_JOINTS   = list(range(23, 35))   # 23-34: unused on 23-DOF

# Control gains — deliberately conservative
KP_ARM   = 20.0   # ~10% of sim Kp=200. Loose tracking.
KD_ARM   = 2.0
KP_LEG   = 0.0    # Legs in pure damping: do not resist gravity while hanging
KD_LEG   = 2.0    # Small damper prevents wild swinging
KP_WAIST = 0.0
KD_WAIST = 2.0
KP_EXT   = 0.0    # Unknown joints: zero torque
KD_EXT   = 0.0

# Safety: abort if any joint velocity exceeds this threshold (rad/s)
VELOCITY_ABORT_THRESHOLD = 8.0

# Control loop frequency (Hz)
CTRL_HZ = 200.0
CTRL_DT = 1.0 / CTRL_HZ

# PKL playback: 30 FPS → every N control ticks we advance one frame
PKL_FPS = 30.0
TICKS_PER_FRAME = int(CTRL_HZ / PKL_FPS)  # = 6 ticks per frame at 200Hz


def _make_cmd(mode_pr: int = 0, mode_machine: int = 0) -> LowCmd_:
    """Allocate a LowCmd_ with static fields initialized. Call once; reuse the object."""
    cmd = LowCmd_default()
    cmd.mode_pr = mode_pr
    cmd.mode_machine = mode_machine
    for i in range(NUM_MOTOR):
        cmd.motor_cmd[i].mode = 0x01  # PMSM
        cmd.motor_cmd[i].q   = 0.0
        cmd.motor_cmd[i].kp  = 0.0
        cmd.motor_cmd[i].dq  = 0.0
        cmd.motor_cmd[i].kd  = 0.0
        cmd.motor_cmd[i].tau = 0.0
    return cmd


# Per-joint gain lookup: motor_index → (kp, kd)
def _build_gain_map(arm_indices: list[int]) -> dict[int, tuple[float, float]]:
    gains: dict[int, tuple[float, float]] = {}
    for i in range(NUM_MOTOR):
        if i in arm_indices:
            gains[i] = (KP_ARM, KD_ARM)
        elif i in LEG_JOINTS or i in WAIST_JOINTS:
            gains[i] = (KP_LEG, KD_LEG)
        else:
            gains[i] = (KP_EXT, KD_EXT)
    return gains


class ArmReplayController:
    def __init__(self, pkl_frames: np.ndarray, arm_indices: list[int]):
        self.frames = pkl_frames
        self.arm_indices = arm_indices
        self.current_state: LowState_ | None = None
        self.aborted = False
        # Pre-allocate command objects — never reallocate in the control loop
        self._cmd      = _make_cmd()
        self._zero_cmd = _make_cmd()
        self._gains    = _build_gain_map(arm_indices)
        self._crc      = CRC()
        # Stamp static gains/positions on _cmd once; only arm q changes per tick
        for i in range(NUM_MOTOR):
            kp, kd = self._gains[i]
            self._cmd.motor_cmd[i].kp = kp
            self._cmd.motor_cmd[i].kd = kd

    def on_low_state(self, msg: LowState_):
        self.current_state = msg

    def _update_cmd(self, target_angles: np.ndarray) -> LowCmd_:
        """Update only arm joint positions in the pre-allocated command object."""
        for i in self.arm_indices:
            self._cmd.motor_cmd[i].q = float(target_angles[i])
        return self._cmd

    def _check_velocity_abort(self, msg: LowState_) -> bool:
        for i in self.arm_indices:
            dq = abs(msg.motor_state[i].dq)
            if dq > VELOCITY_ABORT_THRESHOLD:
                print(f"\n[ABORT] Joint {i} velocity {dq:.2f} rad/s exceeded threshold "
                      f"{VELOCITY_ABORT_THRESHOLD} rad/s. Emergency zero-torque engaged.")
                return True
        return False

    def run(self, publisher: ChannelPublisher):
        total_frames = len(self.frames)
        frame_idx = 0
        tick = 0

        print(f"\nReplaying {total_frames} frames at {PKL_FPS} FPS "
              f"({CTRL_HZ} Hz control loop)")
        print(f"Commanding joints: {self.arm_indices}")
        print(f"Kp={KP_ARM}, Kd={KD_ARM}  |  Abort threshold={VELOCITY_ABORT_THRESHOLD} rad/s")
        print("Press Ctrl+C to stop and engage zero torque.\n")

        try:
            while frame_idx < total_frames:
                loop_start = time.monotonic()

                if self.current_state is None:
                    print("Waiting for first LowState message from robot...")
                    time.sleep(0.1)
                    continue

                # Safety check on every tick
                if self._check_velocity_abort(self.current_state):
                    self.aborted = True
                    break

                target = self.frames[frame_idx]  # shape (35,)
                cmd = self._update_cmd(target)
                cmd.crc = self._crc.Crc(cmd)
                publisher.Write(cmd)

                # Print status at ~5 Hz
                if tick % (CTRL_HZ // 5) == 0:
                    arm_errors = [
                        abs(target[i] - self.current_state.motor_state[i].q)
                        for i in self.arm_indices
                    ]
                    max_err = max(arm_errors)
                    print(f"Frame {frame_idx:>3}/{total_frames}  "
                          f"max_arm_error={max_err:.4f} rad  "
                          f"tick={tick}", end="\r")

                tick += 1
                if tick % TICKS_PER_FRAME == 0:
                    frame_idx += 1

                elapsed = time.monotonic() - loop_start
                sleep_t = CTRL_DT - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)

        except KeyboardInterrupt:
            print("\n\nKeyboard interrupt — engaging zero torque.")

        finally:
            # Always return to zero torque on exit
            print("Sending zero-torque command to all joints...")
            for _ in range(10):  # send several times to ensure delivery
                self._zero_cmd.crc = self._crc.Crc(self._zero_cmd)
                publisher.Write(self._zero_cmd)
                time.sleep(0.01)
            print("Done. Safe to handle robot.")


def load_pkl(pkl_path: str) -> np.ndarray:
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)

    joints = data.get("joint_angles")
    if joints is None:
        raise ValueError("PKL missing 'joint_angles' key")

    joints = np.array(joints, dtype=np.float32)

    if joints.shape[1] != NUM_MOTOR:
        raise ValueError(
            f"PKL has {joints.shape[1]} joints, expected {NUM_MOTOR}. "
            "Verify GMR retargeting output matches G1 hardware IDL ordering."
        )

    if np.isnan(joints).any():
        raise ValueError("PKL contains NaN values — retargeting produced invalid angles.")

    max_angle = np.max(np.abs(joints))
    if max_angle > 2 * np.pi:
        print(f"[WARNING] Max joint angle in PKL is {max_angle:.3f} rad (> 2π). "
              "Hardware joint limits will clip these values.")

    return joints


def main():
    parser = argparse.ArgumentParser(description="G1 Airborne Arm Replay — Low-Gain Kinematic Replay")
    parser.add_argument("--pkl", required=True, help="Path to .pkl file with 35-DOF joint_angles")
    parser.add_argument("--both-arms", action="store_true",
                        help="Command both arms (joints 15-28). Default: left arm only (15-21).")
    parser.add_argument("--interface", default="lo",
                        help="Network interface: 'lo' for simulation, 'eth0' for real hardware")
    parser.add_argument("--domain", type=int, default=0, help="DDS Domain ID (default: 0 for real G1)")
    args = parser.parse_args()

    print("=" * 60)
    print("G1 ARM REPLAY — AIRBORNE LOW-GAIN TEST")
    print("=" * 60)
    print("SAFETY CHECK: Robot must be suspended on gantry.")
    print("SAFETY CHECK: g1_encoder_monitor.py run and joint mapping confirmed.")
    print("SAFETY CHECK: Operator ready on L1+L2 e-stop.")
    print()
    confirm = input("Type 'YES' to proceed: ").strip()
    if confirm != "YES":
        print("Aborted.")
        sys.exit(0)

    # Load and validate pkl
    print(f"\nLoading PKL: {args.pkl}")
    frames = load_pkl(args.pkl)
    print(f"Loaded {len(frames)} frames, {frames.shape[1]} DOF per frame.")

    # Select arm joints to command
    arm_indices = LEFT_ARM + RIGHT_ARM if args.both_arms else LEFT_ARM
    print(f"Commanding: {'both arms' if args.both_arms else 'left arm only'} → indices {arm_indices}")

    # Initialize DDS
    print(f"\nInitializing CycloneDDS on interface '{args.interface}', domain {args.domain}...")
    ChannelFactoryInitialize(args.domain, args.interface)

    controller = ArmReplayController(frames, arm_indices)

    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(controller.on_low_state, 10)

    pub = ChannelPublisher("rt/lowcmd", LowCmd_)
    pub.Init()

    # Brief wait to confirm state subscription is live
    print("Waiting for LowState messages (5s timeout)...")
    deadline = time.monotonic() + 5.0
    while controller.current_state is None and time.monotonic() < deadline:
        time.sleep(0.05)

    if controller.current_state is None:
        print("[ERROR] No LowState received. DDS bridge is not active.")
        print("Check: robot powered on? CYCLONEDDS_HOME set? Interface correct?")
        sys.exit(1)

    print("LowState confirmed. Starting replay in 3 seconds...")
    time.sleep(3.0)

    controller.run(pub)

    if controller.aborted:
        print("\n[RESULT] Replay aborted due to velocity limit. Diagnose before retrying.")
    else:
        print("\n[RESULT] Replay completed.")


if __name__ == "__main__":
    main()
