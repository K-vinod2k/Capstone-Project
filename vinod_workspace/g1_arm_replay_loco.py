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
  4. `--dry-run-map` and `--dry-run-limits` have been executed and inspected.

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

Loco-aware trajectory limiting ([T2]):
  Under rt/arm_sdk, arm motion is a disturbance the balance controller must
  reject. deploy_real.py's 2.0 rad/s inter-frame clamp was tuned for full
  low-level takeover and is too aggressive here. We preserve pose shape
  exactly and negotiate *timing* instead: compute a global slowdown factor k
  such that no commanded arm joint violates --max-arm-vel or --max-arm-jerk
  after playback at user --speed, and apply effective_speed = --speed / k.
  See compute_loco_speed_cap() below.

Usage:
    # 1. Inspect the 23→arm-SDK remap (no DDS):
    python g1_arm_replay_loco.py --pkl wave_kinematics.pkl --dry-run-map

    # 2. Inspect vel/jerk vs caps and required slowdown (no DDS):
    python g1_arm_replay_loco.py --pkl wave_kinematics.pkl --dry-run-limits

    # 3. [Gate A] Readback-only DDS smoke test (run g1_encoder_monitor.py first).

    # 4. [Gate B] Single-joint physical identity jog (no --pkl needed).
    #    Validates the remap maps arm-SDK idx N to the expected physical motor.
    python g1_arm_replay_loco.py --jog-test 19 --jog-amp 0.2 --iface enp0s31f6

    # 5. [Gate C] Engage-only protocol test (no --pkl needed, no arm motion).
    #    Ramps weight 0 → 0.1 → 0 with arms echoing current encoder q.
    python g1_arm_replay_loco.py --engage-only --engage-weight 0.1 --iface enp0s31f6

    # 6. Full hardware run (loco-controlled stance, conservative speed):
    python g1_arm_replay_loco.py --pkl wave_kinematics.pkl --iface enp0s31f6 --speed 0.5

See: kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md for the full procedure.

TODO extension points (tracked in plan g1-loco-arm-integration):
  [T1] IK-based semantic projection for PKLs that do encode wrist motion.
  [T2] DONE: loco-aware trajectory limiting via global speed cap. Preserves
       pose shape; only timing is negotiated to satisfy vel/jerk caps.
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

# [T2] Loco-aware motion limits.
# Starting points (tune from hardware observation):
#   - vel 1.0 rad/s: ~1/2 of deploy_real.py's 2.0 rad/s clamp. Under loco, each
#     rad/s of arm angular velocity at ~2 kg·m^2 arm inertia is ~2 N·m of
#     shoulder torque the balancer must reject.
#   - jerk 5.0 rad/s^3: a step change in arm acceleration couples into CoM as
#     an impulse; keep the third derivative bounded so the balancer sees
#     "smooth" disturbances instead of impulses.
DEFAULT_MAX_ARM_VEL = 1.0   # rad/s per commanded arm joint
DEFAULT_MAX_ARM_JERK = 5.0  # rad/s^3 per commanded arm joint

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


def compute_loco_speed_cap(
    frames: np.ndarray,
    user_speed: float,
    max_vel: float,
    max_jerk: float,
    pkl_fps: float = PKL_FPS,
) -> tuple[float, dict]:
    """
    [T2] Compute an effective playback speed such that no commanded arm joint
    violates --max-arm-vel or --max-arm-jerk at runtime.

    Derivatives are computed once at the PKL sample rate. Under playback at
    speed factor s, the effective values scale as:
        vel_runtime  = vel_pkl  * s
        jerk_runtime = jerk_pkl * s^3
    So the required slowdown k (multiplicative on user_speed) is:
        k_v = (max|vel_pkl|  * user_speed) / max_vel       if > 1, else 1
        k_j = ((max|jerk_pkl| * user_speed^3) / max_jerk)^(1/3) if > 1, else 1
        k   = max(1, k_v, k_j)
        effective_speed = user_speed / k

    Pose shape is preserved exactly; only global timing slows down. This is
    the right trade-off for hero gestures — the pose is the artistic intent,
    the timing is negotiable. The opposite (smoothing amplitudes to keep
    timing) would distort the gesture.

    Returns (effective_speed, diagnostics). `diagnostics` contains per-joint
    peak vel/jerk at both PKL rate and runtime rate, plus the limiting joint.
    """
    if len(frames) < 4:
        return user_speed, {
            "note": "Fewer than 4 frames; cannot compute meaningful jerk.",
            "effective_speed": user_speed,
            "k": 1.0,
            "per_joint": [],
        }

    dt_pkl = 1.0 / pkl_fps
    # Extract only the commanded arm columns from the PKL and apply the sign flip
    # policy so we measure the motion the hardware will actually see.
    pkl_cols = sorted(REMAP_23_TO_ARMSDK.keys())
    q = np.stack([
        -frames[:, c] if c in SIGN_FLIP_PKL_IDX else frames[:, c]
        for c in pkl_cols
    ], axis=1)  # shape (N, 10)

    vel = np.gradient(q, dt_pkl, axis=0)
    acc = np.gradient(vel, dt_pkl, axis=0)
    jerk = np.gradient(acc, dt_pkl, axis=0)

    peak_vel = np.max(np.abs(vel), axis=0)   # per-joint peak vel at PKL rate
    peak_acc = np.max(np.abs(acc), axis=0)
    peak_jerk = np.max(np.abs(jerk), axis=0)  # per-joint peak jerk at PKL rate

    # Worst offender across all commanded arm joints, scaled to user_speed.
    worst_v_runtime = float(np.max(peak_vel) * user_speed)
    worst_j_runtime = float(np.max(peak_jerk) * (user_speed ** 3))

    k_v = worst_v_runtime / max_vel if worst_v_runtime > max_vel else 1.0
    k_j = (worst_j_runtime / max_jerk) ** (1.0 / 3.0) if worst_j_runtime > max_jerk else 1.0
    k = max(1.0, k_v, k_j)
    effective_speed = user_speed / k

    # Per-joint report (names in arm-SDK space for readability on hardware).
    per_joint = []
    for i, pkl_idx in enumerate(pkl_cols):
        armsdk_idx, armsdk_name = REMAP_23_TO_ARMSDK[pkl_idx]
        per_joint.append({
            "pkl_idx": pkl_idx,
            "armsdk_idx": armsdk_idx,
            "armsdk_name": armsdk_name,
            "peak_vel_pkl": float(peak_vel[i]),
            "peak_acc_pkl": float(peak_acc[i]),
            "peak_jerk_pkl": float(peak_jerk[i]),
            "peak_vel_runtime": float(peak_vel[i] * user_speed),
            "peak_jerk_runtime": float(peak_jerk[i] * (user_speed ** 3)),
        })

    diagnostics = {
        "user_speed": user_speed,
        "effective_speed": effective_speed,
        "k": k,
        "k_vel": k_v,
        "k_jerk": k_j,
        "max_vel_cap": max_vel,
        "max_jerk_cap": max_jerk,
        "worst_vel_runtime": worst_v_runtime,
        "worst_jerk_runtime": worst_j_runtime,
        "per_joint": per_joint,
    }
    return effective_speed, diagnostics


def print_limit_report(diag: dict) -> None:
    print("\n[T2] Loco-aware trajectory limit report")
    print("=" * 88)
    print(f"Caps: vel ≤ {diag['max_vel_cap']:.2f} rad/s  |  jerk ≤ {diag['max_jerk_cap']:.2f} rad/s^3")
    print(f"Requested --speed: {diag['user_speed']:.3f}")
    print("-" * 88)
    print(f"{'arm-SDK':<6}{'name':<22}{'v_pkl':>9}{'a_pkl':>9}{'j_pkl':>10}"
          f"{'v_run':>9}{'j_run':>10}{'v_OK':>6}{'j_OK':>6}")
    print("-" * 88)
    for pj in diag["per_joint"]:
        v_ok = "YES" if pj["peak_vel_runtime"] <= diag["max_vel_cap"] else "NO"
        j_ok = "YES" if pj["peak_jerk_runtime"] <= diag["max_jerk_cap"] else "NO"
        print(f"{pj['armsdk_idx']:<6}{pj['armsdk_name']:<22}"
              f"{pj['peak_vel_pkl']:>9.3f}"
              f"{pj['peak_acc_pkl']:>9.3f}"
              f"{pj['peak_jerk_pkl']:>10.3f}"
              f"{pj['peak_vel_runtime']:>9.3f}"
              f"{pj['peak_jerk_runtime']:>10.3f}"
              f"{v_ok:>6}{j_ok:>6}")
    print("-" * 88)
    print(f"Worst at user_speed={diag['user_speed']:.3f}:  "
          f"v_runtime={diag['worst_vel_runtime']:.3f} rad/s   "
          f"j_runtime={diag['worst_jerk_runtime']:.3f} rad/s^3")
    print(f"Slowdown factors:  k_vel={diag['k_vel']:.3f}  k_jerk={diag['k_jerk']:.3f}  "
          f"k_effective={diag['k']:.3f}")
    if diag["k"] > 1.0:
        print(f"[LIMIT ACTIVE] effective_speed = {diag['user_speed']:.3f} / {diag['k']:.3f} "
              f"= {diag['effective_speed']:.3f}")
    else:
        print(f"[WITHIN LIMITS] effective_speed = {diag['effective_speed']:.3f} "
              "(no slowdown applied)")
    print("=" * 88)


class ArmSdkLocoController:
    def __init__(self, frames: np.ndarray | None, speed_factor: float):
        if not SDK_AVAILABLE:
            raise RuntimeError("unitree_sdk2py not importable. Install on the deployment machine.")
        # frames may be None for pre-flight gate modes (engage_only, jog_test)
        # that validate the arm_sdk protocol without streaming a trajectory.
        if frames is None:
            frames = np.zeros((0, NUM_MOTOR), dtype=np.float32)
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
        """Stream mapped PKL frames at active_fps with cubic Hermite interpolation.

        active_fps is set in __init__ from speed_factor, which has already been
        reduced by compute_loco_speed_cap() in main(). So per-joint vel/jerk at
        this playback rate satisfies --max-arm-vel and --max-arm-jerk.
        """
        assert self.current_state is not None
        print(f"[PLAYBACK] Streaming {self.num_frames} frames at {self.active_fps:.1f} fps "
              f"({CTRL_HZ:.0f} Hz control)")
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

    def _wait_for_low_state(self, timeout_s: float = 5.0) -> bool:
        """Block until first LowState arrives (so mode_machine and encoders are populated).
        Returns False on timeout so callers can fail fast without commanding actuators.
        """
        print("Waiting for first LowState from robot...")
        deadline = time.monotonic() + timeout_s
        while self.current_state is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.current_state is None:
            print(f"[ERROR] No LowState received in {timeout_s:.1f}s. "
                  "DDS bridge inactive or wrong --iface.")
            return False
        return True

    def engage_only(self, publisher: ChannelPublisher,
                    max_weight: float = 0.1,
                    hold_seconds: float = 3.0) -> None:
        """Gate C — protocol acceptance test.

        Ramps arm_sdk weight 0 → max_weight → 0 while commanding every arm joint to
        its *current* encoder q each tick (identity controller). Validates that the
        locomotion computer accepts `rt/arm_sdk` publications (CRC, mode_machine,
        weight-bit protocol) WITHOUT commanding any arm motion. A passing run shows
        the robot standing normally with no perceptible arm twitch.

        Failure modes are all safe:
          - Arms don't respond and robot keeps standing → topic not accepted (check
            firmware, --iface, mode_machine capture).
          - Arms subtly stiffen at max_weight → protocol accepted. This is the PASS.
          - Velocity abort triggers → loco is rejecting our commands; this method
            calls _check_velocity_abort every tick and backs out via weight=0.

        Precondition: robot must be in BalanceStand() (loco active), not DAMPING.
        """
        if not self._wait_for_low_state():
            return
        assert self.current_state is not None

        def _identity_targets() -> dict[int, float]:
            return {i: self.current_state.motor_state[i].q for i in COMMANDED_ARMSDK_INDICES}

        total_s = ENGAGE_SECONDS + hold_seconds + RELEASE_SECONDS
        print(f"\n[ENGAGE-ONLY] weight 0 → {max_weight:.2f} → 0 over {total_s:.1f}s; "
              "arm targets = current encoder q (no motion commanded).")
        print("[ENGAGE-ONLY] Expected PASS = robot stands normally, no arm twitch.")

        ticks_up = int(ENGAGE_SECONDS * CTRL_HZ)
        for tick in range(ticks_up):
            loop_start = time.monotonic()
            if self._check_velocity_abort(self.current_state):
                self.aborted = True
                break
            alpha = cubic_ease(tick / float(ticks_up))
            self._set_weight(alpha * max_weight)
            self._apply_targets(_identity_targets())
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

        if not self.aborted:
            print(f"[ENGAGE-ONLY] Holding weight={max_weight:.2f} for {hold_seconds}s "
                  "(observe: robot should remain stable, arms should not move).")
            ticks_hold = int(hold_seconds * CTRL_HZ)
            for _ in range(ticks_hold):
                loop_start = time.monotonic()
                if self._check_velocity_abort(self.current_state):
                    self.aborted = True
                    break
                self._set_weight(max_weight)
                self._apply_targets(_identity_targets())
                self._write(publisher)
                time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

        print(f"[ENGAGE-ONLY] Ramping weight {max_weight:.2f} → 0 over {RELEASE_SECONDS}s...")
        ticks_down = int(RELEASE_SECONDS * CTRL_HZ)
        for tick in range(ticks_down):
            loop_start = time.monotonic()
            s = tick / float(ticks_down)
            self._set_weight(max_weight * (1.0 - cubic_ease(s)))
            self._apply_targets(_identity_targets())
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))
        self._set_weight(0.0)
        for _ in range(10):
            self._write(publisher)
            time.sleep(0.01)
        print("[ENGAGE-ONLY] Done. Loco has full authority.")

    def jog_test(self, publisher: ChannelPublisher,
                 target_armsdk_idx: int,
                 amplitude: float = 0.2,
                 hold_seconds: float = 2.0) -> None:
        """Gate B — single-joint physical identity jog.

        Commands ONE arm-SDK joint by +amplitude rad from its current encoder q,
        holds for `hold_seconds`, returns to start, then releases. All OTHER arm
        joints hold their current encoder q throughout. Validates that arm-SDK
        index `target_armsdk_idx` drives the *physical motor* the remap table
        claims it does.

        Critical use case: the remap assumes "23-DOF L_ELBOW_ROLL ≡ arm-SDK
        L_WRIST_ROLL is the same physical motor" (PKL idx 17 → arm-SDK idx 19).
        This has NEVER been directly proven on a specific robot — only inferred
        from Unitree's 23DOF/29DOF chassis-sharing convention. Jogging arm-SDK
        idx 19 and observing which joint physically moves closes that gap.

        Suggested first-jog targets (safest, smallest arm-of-moment):
          15 = L_SHOULDER_PITCH  (unambiguous; confirms L-arm wiring)
          19 = L_WRIST_ROLL      (the key ELBOW_ROLL ≡ WRIST_ROLL test)
          22 = R_SHOULDER_PITCH  (confirms R-arm wiring; side-swap check)

        Precondition: robot in BalanceStand(), gantry attached, operator on E-stop.
        """
        if target_armsdk_idx not in COMMANDED_ARMSDK_INDICES:
            print(f"[ERROR] arm-SDK idx {target_armsdk_idx} is not in the commanded set "
                  f"{COMMANDED_ARMSDK_INDICES}. Refusing to jog.")
            return
        if not self._wait_for_low_state():
            return
        assert self.current_state is not None

        name_lookup = {m: n for _, (m, n) in REMAP_23_TO_ARMSDK.items()}
        name = name_lookup.get(target_armsdk_idx, f"armsdk_{target_armsdk_idx}")
        start_q = {i: self.current_state.motor_state[i].q for i in COMMANDED_ARMSDK_INDICES}
        target_q = dict(start_q)
        target_q[target_armsdk_idx] = start_q[target_armsdk_idx] + amplitude

        print(f"\n[JOG-TEST] arm-SDK idx={target_armsdk_idx} ({name})")
        print(f"[JOG-TEST] q_start={start_q[target_armsdk_idx]:+.3f} rad  →  "
              f"q_target={target_q[target_armsdk_idx]:+.3f} rad  (Δ={amplitude:+.3f} rad)")
        print(f"[JOG-TEST] OBSERVE PHYSICALLY: expect {name} to move by ~{amplitude} rad.")
        print("[JOG-TEST] If a DIFFERENT joint moves, the remap is wrong — abort with Ctrl-C.")

        ticks_engage = int(ENGAGE_SECONDS * CTRL_HZ)
        for tick in range(ticks_engage):
            loop_start = time.monotonic()
            if self._check_velocity_abort(self.current_state):
                self.aborted = True
                break
            alpha = cubic_ease(tick / float(ticks_engage))
            self._set_weight(alpha)
            interp = {i: (1.0 - alpha) * start_q[i] + alpha * target_q[i]
                      for i in COMMANDED_ARMSDK_INDICES}
            self._apply_targets(interp)
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

        if not self.aborted:
            print(f"[JOG-TEST] Holding target for {hold_seconds}s...")
            ticks_hold = int(hold_seconds * CTRL_HZ)
            for _ in range(ticks_hold):
                loop_start = time.monotonic()
                if self._check_velocity_abort(self.current_state):
                    self.aborted = True
                    break
                self._set_weight(1.0)
                self._apply_targets(target_q)
                self._write(publisher)
                time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

        print(f"[JOG-TEST] Returning to start q over {EASE_OUT_SECONDS}s...")
        ticks_back = int(EASE_OUT_SECONDS * CTRL_HZ)
        for tick in range(ticks_back):
            loop_start = time.monotonic()
            alpha = cubic_ease(tick / float(ticks_back))
            interp = {i: (1.0 - alpha) * target_q[i] + alpha * start_q[i]
                      for i in COMMANDED_ARMSDK_INDICES}
            self._apply_targets(interp)
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))

        print(f"[JOG-TEST] Releasing arm_sdk weight over {RELEASE_SECONDS}s...")
        ticks_rel = int(RELEASE_SECONDS * CTRL_HZ)
        for tick in range(ticks_rel):
            loop_start = time.monotonic()
            s = tick / float(ticks_rel)
            self._set_weight(1.0 - cubic_ease(s))
            self._apply_targets(start_q)
            self._write(publisher)
            time.sleep(max(0.0, CTRL_DT - (time.monotonic() - loop_start)))
        self._set_weight(0.0)
        for _ in range(10):
            self._write(publisher)
            time.sleep(0.01)
        print("[JOG-TEST] Done. Loco has full authority.")

    def run(self, publisher: ChannelPublisher) -> None:
        if not self._wait_for_low_state():
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
    parser.add_argument("--pkl", default=None,
                        help="Path to 23-DOF .pkl (joint_angles key). "
                             "Required for full playback; ignored for --engage-only / --jog-test.")
    parser.add_argument("--iface", default="enp0s31f6",
                        help="Network interface (default: enp0s31f6 for iotlab Linux)")
    parser.add_argument("--domain", type=int, default=0, help="DDS Domain ID (default: 0)")
    parser.add_argument("--speed", type=float, default=0.5,
                        help="PKL playback speed multiplier (default: 0.5 — conservative first run). "
                             "May be reduced further by --max-arm-vel / --max-arm-jerk.")
    parser.add_argument("--max-arm-vel", type=float, default=DEFAULT_MAX_ARM_VEL,
                        help=f"[T2] Per-joint arm vel cap (rad/s) at runtime. "
                             f"Default: {DEFAULT_MAX_ARM_VEL}")
    parser.add_argument("--max-arm-jerk", type=float, default=DEFAULT_MAX_ARM_JERK,
                        help=f"[T2] Per-joint arm jerk cap (rad/s^3) at runtime. "
                             f"Default: {DEFAULT_MAX_ARM_JERK}")
    parser.add_argument("--dry-run-map", action="store_true",
                        help="Print the 23→arm-SDK remap for the first frame and exit without DDS.")
    parser.add_argument("--dry-run-limits", action="store_true",
                        help="Compute vel/jerk against caps, report required slowdown, and exit without DDS.")
    parser.add_argument("--ignore-loco-limits", action="store_true",
                        help="Skip --max-arm-vel / --max-arm-jerk check (use only for debugging).")
    parser.add_argument("--engage-only", action="store_true",
                        help="Gate C: ramp arm_sdk weight 0 → --engage-weight → 0 while commanding "
                             "current encoder q on all arm joints. Validates topic acceptance without motion. "
                             "No --pkl required.")
    parser.add_argument("--engage-weight", type=float, default=0.1,
                        help="Max weight for --engage-only (default: 0.1 — small on first run).")
    parser.add_argument("--jog-test", type=int, default=None, metavar="ARMSDK_IDX",
                        help="Gate B: command ONE arm-SDK joint by --jog-amp rad "
                             "(15=L_SHOULDER_PITCH, 19=L_WRIST_ROLL, 22=R_SHOULDER_PITCH, ...). "
                             "Validates physical motor identity of the remap. No --pkl required.")
    parser.add_argument("--jog-amp", type=float, default=0.2,
                        help="Jog amplitude in rad for --jog-test (default: 0.2).")
    args = parser.parse_args()

    gate_mode = args.engage_only or (args.jog_test is not None)
    if args.engage_only and args.jog_test is not None:
        print("[ERROR] --engage-only and --jog-test are mutually exclusive.")
        return 1

    frames = None
    effective_speed = args.speed
    if gate_mode:
        print(f"[GATE-MODE] --pkl is ignored. Running "
              f"{'--engage-only' if args.engage_only else f'--jog-test {args.jog_test}'}.")
    else:
        if args.pkl is None:
            print("[ERROR] --pkl is required for full playback "
                  "(or pass --engage-only / --jog-test for pre-flight gates).")
            return 1
        if not Path(args.pkl).exists():
            print(f"[ERROR] PKL not found: {args.pkl}")
            return 1
        frames = load_pkl(args.pkl)
        print(f"Loaded {len(frames)} frames × {frames.shape[1]} cols from {args.pkl}")
        print_remap_table(frames[0])

        if args.dry_run_map:
            print("\n[DRY-RUN] --dry-run-map set; exiting before limits and DDS init.")
            return 0

        # [T2] Loco-aware speed negotiation. Pose shape stays intact.
        if args.ignore_loco_limits:
            print("\n[WARN] --ignore-loco-limits: skipping T2 trajectory limiting. "
                  "Hardware may destabilize the balance controller.")
            effective_speed = args.speed
        else:
            effective_speed, diag = compute_loco_speed_cap(
                frames, args.speed, args.max_arm_vel, args.max_arm_jerk
            )
            print_limit_report(diag)

        if args.dry_run_limits:
            print("\n[DRY-RUN] --dry-run-limits set; exiting before DDS init.")
            return 0

    if not SDK_AVAILABLE:
        print("\n[ERROR] unitree_sdk2py not importable. Install on the deployment machine:")
        print("  git clone https://github.com/unitreerobotics/unitree_sdk2_python.git")
        print("  cd unitree_sdk2_python && pip install -e .")
        return 1

    print("=" * 60)
    if args.engage_only:
        print("GATE C — ENGAGE-ONLY PROTOCOL TEST  (no arm motion commanded)")
    elif args.jog_test is not None:
        print(f"GATE B — SINGLE-JOINT JOG  (arm-SDK idx={args.jog_test}, Δ={args.jog_amp:+.3f} rad)")
    else:
        print("G1 ARM REPLAY via rt/arm_sdk  (locomotion preserved)")
    print("=" * 60)
    print("SAFETY CHECK: Robot in BalanceStand() (loco active, NOT damping).")
    print("SAFETY CHECK: Operator ready on L1+L2 e-stop.")
    if gate_mode:
        print("SAFETY CHECK: Gantry attached recommended for first hardware run.")
    else:
        print(f"SAFETY CHECK: requested --speed={args.speed}, "
              f"effective={effective_speed:.3f} after loco limits.")
    confirm = input("\nType 'YES' to proceed: ").strip()
    if confirm != "YES":
        print("Aborted.")
        return 0

    ChannelFactoryInitialize(args.domain, args.iface)
    controller = ArmSdkLocoController(frames, effective_speed)
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(controller.on_low_state, 10)
    pub = ChannelPublisher("rt/arm_sdk", LowCmd_)
    pub.Init()

    try:
        if args.engage_only:
            controller.engage_only(pub, max_weight=args.engage_weight)
        elif args.jog_test is not None:
            controller.jog_test(pub, target_armsdk_idx=args.jog_test,
                                amplitude=args.jog_amp)
        else:
            controller.run(pub)
    except KeyboardInterrupt:
        print("\n[KEYBOARD INTERRUPT] Forcing ease-out and release.")
        controller.aborted = True
        # ease_out_and_release assumes a prior playback; for gate modes, just
        # ramp the weight to zero on whatever target is currently set.
        if args.engage_only or args.jog_test is not None:
            for tick in range(int(RELEASE_SECONDS * CTRL_HZ)):
                s = tick / float(int(RELEASE_SECONDS * CTRL_HZ))
                controller._set_weight(1.0 - cubic_ease(s))
                controller._write(pub)
                time.sleep(CTRL_DT)
            controller._set_weight(0.0)
            for _ in range(10):
                controller._write(pub)
                time.sleep(0.01)
        else:
            controller.ease_out_and_release(pub)
    return 1 if controller.aborted else 0


if __name__ == "__main__":
    sys.exit(main())
