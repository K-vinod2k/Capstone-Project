"""
g1_arm_replay_loco.py — G1 Arm Replay via rt/arm_sdk (locomotion-preserving)
---------------------------------------------------------------------------
Command hero-gesture arm trajectories on the Unitree G1 WITHOUT releasing the
built-in locomotion controller. Publishes on `rt/arm_sdk`; the locomotion
task keeps ownership of legs (0-11), torso (12), and runs the servo loop.

SAFETY PRECONDITIONS (do not skip):
  1. Robot is in a stable stance (BalanceStand() or equivalent) BEFORE running.
  2. Operator holds physical L1+L2 E-Stop.
  3. First run uses `--speed 0.5` and small-amplitude PKLs (e.g. wave).
  4. `--dry-run-map` has been executed and the remap table inspected.

Contract (derived from unitree_sdk2_python_repo g1_arm7_sdk_dds_example.py):
  - Publisher: `rt/arm_sdk` (NOT `rt/lowcmd`).
  - Enable weight: motor_cmd[29].q ∈ [0, 1], ramped 0→1 to engage, 1→0 to release.
  - Command arm joints only (indices 15-28 in 29-index IDL). Legs/waist untouched.
  - tau_ff = 0.0 on every arm joint: the loco controller owns gravity compensation.
  - Control rate: 50 Hz (loco controller runs its own high-rate servo loop beneath).
  - CRC recomputed before every Write(). mode_machine echoed from first LowState.

23-DOF → 29-index arm-SDK semantic remap (see REMAP table below):
  23-DOF IDL stores each arm as shoulder(3) + elbow_pitch + elbow_roll. The
  arm-SDK 29-index IDL labels the same five motors as shoulder(3) + elbow +
  wrist_roll. It is the *same physical motor chain* with a relabelled final
  axis — no IK projection is needed. Wrist_pitch/yaw (20, 21, 27, 28) do not
  exist on 23-DOF hardware and are never commanded.

R_SHOULDER_ROLL sign flip (23-DOF idx 19) is preserved from deploy_real.py:
  the right arm motor is physically mirrored; negation restores symmetry.

Usage:
    python g1_arm_replay_loco.py --pkl ../kim_workspace/movements/wave_kinematics.pkl --dry-run-map
    python g1_arm_replay_loco.py --pkl ../kim_workspace/movements/wave_kinematics.pkl --iface eth0 --speed 0.5

TODO extension points (tracked in plan g1-loco-arm-integration):
  [T1] IK-based semantic projection for PKLs that do encode wrist motion.
  [T2] Locomotion-aware trajectory limiting (tighter velocity/jerk caps than
       full-takeover replay, since arm motion is a disturbance to the balancer).
  [T3] Optional arm gravity compensation layered on top of loco FF.
"""

from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

import numpy as np

try:
    from unitree_sdk2py.core.channel import (
        ChannelFactoryInitialize,
        ChannelPublisher,
        ChannelSubscriber,
    )
    from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_ as LowCmd_default
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
    from unitree_sdk2py.utils.crc import CRC
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


NUM_MOTOR = 35

# arm-SDK enable bit location per SDK reference (g1_arm7_sdk_dds_example.py: kNotUsedJoint = 29).
# motor_cmd[29].q ∈ [0, 1] weights arm-task authority vs locomotion.
ARM_SDK_WEIGHT_IDX = 29

# 23-DOF PKL column index → 29-index arm-SDK motor index.
# Both arms are a 5-DOF chain on 23-DOF hardware (shoulder×3 + elbow_pitch + elbow_roll).
# The arm-SDK IDL labels the final motor "wrist_roll" but it is the SAME physical axis.
# Wrist_pitch/yaw (arm-SDK idx 20, 21, 27, 28) do not exist on 23-DOF hardware.
REMAP_23_TO_ARMSDK: dict[int, tuple[int, str]] = {
    13: (15, "L_SHOULDER_PITCH"),
    14: (16, "L_SHOULDER_ROLL"),
    15: (17, "L_SHOULDER_YAW"),
    16: (18, "L_ELBOW"),          # 23-DOF L_ELBOW_PITCH ≡ arm-SDK L_ELBOW
    17: (19, "L_WRIST_ROLL"),     # 23-DOF L_ELBOW_ROLL ≡ arm-SDK L_WRIST_ROLL (same motor)
    18: (22, "R_SHOULDER_PITCH"),
    19: (23, "R_SHOULDER_ROLL"),  # sign-flipped below
    20: (24, "R_SHOULDER_YAW"),
    21: (25, "R_ELBOW"),
    22: (26, "R_WRIST_ROLL"),
}
# 23-DOF PKL indices whose sign must be inverted before hardware commanding.
# R_SHOULDER_ROLL: right arm motor is physically mirrored vs left (see deploy_real.py:174, 239).
SIGN_FLIP_PKL_IDX = {19}

# Invalid on 23-DOF hardware — NEVER commanded on this build.
INVALID_23DOF_ARMSDK_IDX = {20, 21, 27, 28}  # L/R wrist_pitch, L/R wrist_yaw

# Arm-SDK motor indices we actually drive. Order preserved for deterministic iteration.
COMMANDED_ARMSDK_INDICES = sorted({m for _, (m, _) in REMAP_23_TO_ARMSDK.items()})

# Gains match the SDK reference and the KP_ARM tier in deploy_real.py.
# Loco controller still runs its servo loop; these are the arm-task targets.
KP_ARM = 60.0
KD_ARM = 1.5

# Safety: instant torque-kill if any commanded arm joint exceeds this speed.
VELOCITY_ABORT_THRESHOLD = 8.0  # rad/s

CTRL_HZ = 50.0
CTRL_DT = 1.0 / CTRL_HZ
PKL_FPS = 30.0
ENGAGE_SECONDS = 3.0   # weight 0 → 1 ramp (arm-task authority grows)
EASE_IN_SECONDS = 3.0  # current encoder q → first mapped PKL frame
EASE_OUT_SECONDS = 3.0
RELEASE_SECONDS = 1.0  # weight 1 → 0 ramp (loco resumes full authority)


def cubic_ease(s: float) -> float:
    """3s² - 2s³ cubic easing (C¹, v=0 at both ends). Matches deploy_real.py convention."""
    s = max(0.0, min(1.0, s))
    return 3.0 * s * s - 2.0 * s * s * s


def remap_frame(pkl_frame: np.ndarray) -> dict[int, float]:
    """
    Map a single PKL frame (23-DOF layout, shape (35,) or (23,)) to arm-SDK targets.
    Returns {armsdk_motor_idx: q_target}. Invalid-on-23DOF indices never appear.
    """
    targets: dict[int, float] = {}
    for pkl_idx, (armsdk_idx, _name) in REMAP_23_TO_ARMSDK.items():
        if pkl_idx >= len(pkl_frame):
            continue
        q = float(pkl_frame[pkl_idx])
        if pkl_idx in SIGN_FLIP_PKL_IDX:
            q = -q
        targets[armsdk_idx] = q
    return targets


def load_pkl(pkl_path: str) -> np.ndarray:
    """Load a 23-DOF layout PKL. Accepts 35-column `joint_angles` (standard) or 23-column arrays."""
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)
    if isinstance(data, dict):
        frames = data.get("joint_angles")
        if frames is None:
            frames = data.get("dof_pos")
        if frames is None:
            raise ValueError(f"PKL has no 'joint_angles' or 'dof_pos' key. Keys: {list(data.keys())}")
    else:
        frames = data
    frames = np.asarray(frames, dtype=np.float32)
    if frames.ndim != 2:
        raise ValueError(f"Expected 2D frame array, got shape {frames.shape}")
    ncol = frames.shape[1]
    if ncol not in (23, 29, 35):
        raise ValueError(f"Unexpected PKL column count {ncol}; expected 23, 29, or 35.")
    if ncol == 29:
        raise ValueError(
            "29-column PKL detected (GMR 29-DOF layout). This script consumes 23-DOF PKLs. "
            "Run clamp/remap step first or use a PKL from kim_workspace/movements/."
        )
    if np.isnan(frames).any():
        raise ValueError("PKL contains NaN values.")
    return frames


def print_remap_table(first_frame: np.ndarray) -> None:
    print("\n23-DOF PKL → arm-SDK remap table")
    print("=" * 78)
    print(f"{'PKL idx':<9}{'23-DOF name':<22}{'→ arm-SDK idx':<16}{'arm-SDK name':<20}{'q[rad]':>9}")
    print("-" * 78)
    name_23 = {
        13: "L_SHOULDER_PITCH", 14: "L_SHOULDER_ROLL", 15: "L_SHOULDER_YAW",
        16: "L_ELBOW_PITCH", 17: "L_ELBOW_ROLL",
        18: "R_SHOULDER_PITCH", 19: "R_SHOULDER_ROLL", 20: "R_SHOULDER_YAW",
        21: "R_ELBOW_PITCH", 22: "R_ELBOW_ROLL",
    }
    for pkl_idx, (armsdk_idx, armsdk_name) in REMAP_23_TO_ARMSDK.items():
        q = float(first_frame[pkl_idx]) if pkl_idx < len(first_frame) else float("nan")
        if pkl_idx in SIGN_FLIP_PKL_IDX:
            q_applied = -q
            note = f"  (sign flip: {q:+.3f} → {q_applied:+.3f})"
            q_show = q_applied
        else:
            note = ""
            q_show = q
        print(f"{pkl_idx:<9}{name_23[pkl_idx]:<22}{armsdk_idx:<16}{armsdk_name:<20}{q_show:>9.3f}{note}")
    print("-" * 78)
    print(f"Uncommanded on 23-DOF hardware: {sorted(INVALID_23DOF_ARMSDK_IDX)} "
          "(L/R wrist_pitch, L/R wrist_yaw — no physical motors)")
    print(f"Enable weight bit: motor_cmd[{ARM_SDK_WEIGHT_IDX}].q (ramped 0→1 on engage, 1→0 on release)")
    print("=" * 78)


class ArmSdkLocoController:
    def __init__(self, frames: np.ndarray, speed_factor: float):
        if not SDK_AVAILABLE:
            raise RuntimeError("unitree_sdk2py not importable. Install on the deployment machine.")
        self.frames = frames
        self.speed_factor = speed_factor
        self.active_fps = PKL_FPS * speed_factor
        self.num_frames = len(frames)
        self.current_state: LowState_ | None = None
        self._mode_machine: int | None = None
        self.aborted = False

        self._cmd: LowCmd_ = LowCmd_default()
        self._cmd.mode_pr = 0
        self._cmd.mode_machine = 0
        for i in range(NUM_MOTOR):
            self._cmd.motor_cmd[i].mode = 0x01
            self._cmd.motor_cmd[i].q = 0.0
            self._cmd.motor_cmd[i].dq = 0.0
            self._cmd.motor_cmd[i].kp = 0.0
            self._cmd.motor_cmd[i].kd = 0.0
            self._cmd.motor_cmd[i].tau = 0.0
        # Static gains on commanded arm joints only. Everything else stays at kp=kd=0
        # so the loco controller keeps full authority over legs/waist.
        for armsdk_idx in COMMANDED_ARMSDK_INDICES:
            self._cmd.motor_cmd[armsdk_idx].kp = KP_ARM
            self._cmd.motor_cmd[armsdk_idx].kd = KD_ARM
        self._crc = CRC()

    def on_low_state(self, msg: LowState_) -> None:
        self.current_state = msg
        if self._mode_machine is None:
            self._mode_machine = msg.mode_machine
            self._cmd.mode_machine = self._mode_machine
            print(f"[DDS] mode_machine={self._mode_machine} captured from robot")

    def _check_velocity_abort(self, msg: LowState_) -> bool:
        for armsdk_idx in COMMANDED_ARMSDK_INDICES:
            dq = abs(msg.motor_state[armsdk_idx].dq)
            if dq > VELOCITY_ABORT_THRESHOLD:
                print(f"\n[CRITICAL ABORT] arm-SDK joint {armsdk_idx} dq={dq:.2f} rad/s "
                      f"> {VELOCITY_ABORT_THRESHOLD}. Releasing arm_sdk authority.")
                return True
        return False

    def _set_weight(self, weight: float) -> None:
        self._cmd.motor_cmd[ARM_SDK_WEIGHT_IDX].q = float(np.clip(weight, 0.0, 1.0))

    def _apply_targets(self, targets: dict[int, float]) -> None:
        for armsdk_idx, q in targets.items():
            self._cmd.motor_cmd[armsdk_idx].q = q
            # tau stays 0: loco controller owns gravity compensation.
            # [T3] Optional arm gravity FF would go here if loco FF proves insufficient.

    def _write(self, publisher: ChannelPublisher) -> None:
        self._cmd.crc = self._crc.Crc(self._cmd)
        publisher.Write(self._cmd)

    def engage_and_ease_in(self, publisher: ChannelPublisher) -> None:
        """Ramp arm-SDK weight 0→1 AND interpolate current encoder q → first mapped PKL frame.

        Both ramps run concurrently over ENGAGE_SECONDS so the loco controller hands
        over authority at the same rate we slew into the starting pose — this avoids
        a torque spike at weight=1 with a non-matching target.
        """
        assert self.current_state is not None
        print(f"\n[ENGAGE] Ramping arm_sdk weight 0→1 and easing to first PKL frame "
              f"over {ENGAGE_SECONDS}s...")
        start_q = {i: self.current_state.motor_state[i].q for i in COMMANDED_ARMSDK_INDICES}
        target_q = remap_frame(self.frames[0])
        ticks = int(ENGAGE_SECONDS * CTRL_HZ)
        for tick in range(ticks):
            loop_start = time.monotonic()
            if self._check_velocity_abort(self.current_state):
                self.aborted = True
                return
            s = tick / float(ticks)
            alpha = cubic_ease(s)
            self._set_weight(alpha)
            interp = {
                i: (1.0 - alpha) * start_q[i] + alpha * target_q.get(i, start_q[i])
                for i in COMMANDED_ARMSDK_INDICES
            }
            self._apply_targets(interp)
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

    def playback(self, publisher: ChannelPublisher) -> None:
        """Stream mapped PKL frames at active_fps with cubic Hermite interpolation."""
        assert self.current_state is not None
        print(f"[PLAYBACK] Streaming {self.num_frames} frames at {self.active_fps:.1f} fps "
              f"({CTRL_HZ:.0f} Hz control)")
        # [T2] TODO: loco-aware trajectory limiting (tighter velocity/jerk caps here).
        # Precompute central-difference velocities for Hermite interp (same as deploy_real.py).
        vel = np.zeros_like(self.frames)
        for i in range(1, self.num_frames - 1):
            vel[i] = (self.frames[i + 1] - self.frames[i - 1]) / 2.0
        start_time = time.monotonic()
        while not self.aborted:
            loop_start = time.monotonic()
            if self._check_velocity_abort(self.current_state):
                self.aborted = True
                break
            t = loop_start - start_time
            float_idx = t * self.active_fps
            if float_idx >= self.num_frames - 1:
                break
            idx0 = int(float_idx)
            idx1 = idx0 + 1
            a = float_idx - idx0
            h00 = 2 * a**3 - 3 * a**2 + 1
            h10 = a**3 - 2 * a**2 + a
            h01 = -2 * a**3 + 3 * a**2
            h11 = a**3 - a**2
            frame = h00 * self.frames[idx0] + h10 * vel[idx0] + h01 * self.frames[idx1] + h11 * vel[idx1]
            self._apply_targets(remap_frame(frame))
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

    def ease_out_and_release(self, publisher: ChannelPublisher) -> None:
        """Ease commanded arms back to current encoder state, then ramp weight 1→0."""
        assert self.current_state is not None
        print(f"\n[EASE-OUT] Returning to current stance over {EASE_OUT_SECONDS}s...")
        last_cmd_q = {i: self._cmd.motor_cmd[i].q for i in COMMANDED_ARMSDK_INDICES}
        neutral_q = {i: self.current_state.motor_state[i].q for i in COMMANDED_ARMSDK_INDICES}
        ticks = int(EASE_OUT_SECONDS * CTRL_HZ)
        for tick in range(ticks):
            loop_start = time.monotonic()
            s = tick / float(ticks)
            alpha = cubic_ease(s)
            interp = {
                i: (1.0 - alpha) * last_cmd_q[i] + alpha * neutral_q[i]
                for i in COMMANDED_ARMSDK_INDICES
            }
            self._apply_targets(interp)
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

        print(f"[RELEASE] Ramping arm_sdk weight 1→0 over {RELEASE_SECONDS}s "
              "(loco resumes full authority)...")
        ticks = int(RELEASE_SECONDS * CTRL_HZ)
        for tick in range(ticks):
            loop_start = time.monotonic()
            s = tick / float(ticks)
            self._set_weight(1.0 - cubic_ease(s))
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))
        self._set_weight(0.0)
        for _ in range(10):
            self._write(publisher)
            time.sleep(0.01)
        print("[DONE] arm_sdk released. Locomotion controller has full authority.")

    def run(self, publisher: ChannelPublisher) -> None:
        print("Waiting for first LowState from robot...")
        deadline = time.monotonic() + 5.0
        while self.current_state is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.current_state is None:
            print("[ERROR] No LowState received in 5s. DDS bridge inactive.")
            return
        self.engage_and_ease_in(publisher)
        if self.aborted:
            self.ease_out_and_release(publisher)
            return
        self.playback(publisher)
        self.ease_out_and_release(publisher)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="G1 arm replay via rt/arm_sdk (preserves locomotion).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pkl", required=True, help="Path to 23-DOF .pkl (joint_angles key)")
    parser.add_argument("--iface", default="enp0s31f6",
                        help="Network interface (default: enp0s31f6 for iotlab Linux)")
    parser.add_argument("--domain", type=int, default=0, help="DDS Domain ID (default: 0)")
    parser.add_argument("--speed", type=float, default=0.5,
                        help="PKL playback speed multiplier (default: 0.5 — conservative first run)")
    parser.add_argument("--dry-run-map", action="store_true",
                        help="Print the 23→arm-SDK remap for the first frame and exit without DDS.")
    args = parser.parse_args()

    if not Path(args.pkl).exists():
        print(f"[ERROR] PKL not found: {args.pkl}")
        return 1
    frames = load_pkl(args.pkl)
    print(f"Loaded {len(frames)} frames × {frames.shape[1]} cols from {args.pkl}")

    print_remap_table(frames[0])

    if args.dry_run_map:
        print("\n[DRY-RUN] --dry-run-map set; exiting before DDS init.")
        return 0

    if not SDK_AVAILABLE:
        print("\n[ERROR] unitree_sdk2py not importable. Install on the deployment machine:")
        print("  git clone https://github.com/unitreerobotics/unitree_sdk2_python.git")
        print("  cd unitree_sdk2_python && pip install -e .")
        return 1

    print("=" * 60)
    print("G1 ARM REPLAY via rt/arm_sdk  (locomotion preserved)")
    print("=" * 60)
    print("SAFETY CHECK: Robot in BalanceStand() or equivalent.")
    print("SAFETY CHECK: Operator ready on L1+L2 e-stop.")
    print(f"SAFETY CHECK: speed={args.speed}  ( < 1.0 recommended on first hardware run )")
    confirm = input("\nType 'YES' to proceed: ").strip()
    if confirm != "YES":
        print("Aborted.")
        return 0

    ChannelFactoryInitialize(args.domain, args.iface)
    controller = ArmSdkLocoController(frames, args.speed)
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(controller.on_low_state, 10)
    pub = ChannelPublisher("rt/arm_sdk", LowCmd_)
    pub.Init()

    try:
        controller.run(pub)
    except KeyboardInterrupt:
        print("\n[KEYBOARD INTERRUPT] Forcing ease-out and release.")
        controller.aborted = True
        controller.ease_out_and_release(pub)
    return 1 if controller.aborted else 0


if __name__ == "__main__":
    sys.exit(main())
