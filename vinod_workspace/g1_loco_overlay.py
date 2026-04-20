"""g1_loco_overlay.py - No-fall G1 controller for the persona demo.

The robot's OEM locomotion stabilizer (running on 192.168.123.161) is NEVER
disabled by this script. Every method exposed by G1NoFallController is
physically safe by construction: the legs are always under Unitree's
closed-loop balance controller (1 kHz MPC + IMU + foot force), while our
custom arm gestures ride on top via the rt/arm_sdk weight-blend topic.

This is the hybrid control pattern documented in:
  - Unitree G1 Stabilization Research.docx, Section 3.2 (G1Pilot pattern)
  - unitree_sdk2_python_repo/example/g1/high_level/g1_loco_client_example.py
  - unitree_sdk2_python_repo/example/g1/high_level/g1_arm7_sdk_dds_example.py
  - unitree_sdk2_python_repo/example/g1/high_level/g1_arm_action_example.py

Three tiers of safe control are exposed:

    Tier 1 - Locomotion (LocoClient):
        stand(), walk(), damp(), zero_torque()

    Tier 2 - Canned gestures (G1ArmActionClient):
        canned_gesture("wave"|"hug"|"heart"|"shake hand"|...)

    Tier 3 - Custom PKL arm gestures (rt/arm_sdk overlay):
        play_arm_gesture(pkl_path)

Tier 3 is what makes this file non-trivial: it streams our 23-DOF IDL hero
PKLs onto the robot's arm joints (29-slot DDS indices 15..19 + 22..26 +
optional waist_yaw @ 12) while the weight-blend bit at motor_cmd[29].q
ramps 0 -> 1 -> 0 for a smooth handoff.

Usage:
    python g1_loco_overlay.py <iface>                  # interactive menu
    python g1_loco_overlay.py <iface> --pkl <path.pkl> # one-shot hero play

Examples:
    python g1_loco_overlay.py enp0s31f6
    python g1_loco_overlay.py enp0s31f6 \\
        --pkl kim_workspace/movements/wave_kinematics.pkl
"""

from __future__ import annotations

import argparse
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize,
    ChannelPublisher,
    ChannelSubscriber,
)
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.utils.crc import CRC
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient, action_map


# ---------------------------------------------------------------------------
# Joint map (29-slot DDS motor_cmd array, Unitree G1 official layout)
# ---------------------------------------------------------------------------

class G1JointIndex:
    """29-slot DDS motor_cmd array indices. INVALID slots are locked on 23-DOF."""
    # Legs 0..11 - owned by OEM loco controller. We NEVER write these.
    WaistYaw = 12
    WaistRoll = 13     # INVALID for 23-DOF
    WaistPitch = 14    # INVALID for 23-DOF
    LeftShoulderPitch = 15
    LeftShoulderRoll = 16
    LeftShoulderYaw = 17
    LeftElbow = 18
    LeftWristRoll = 19          # == 23-DOF "elbow_roll"
    LeftWristPitch = 20         # INVALID for 23-DOF
    LeftWristYaw = 21           # INVALID for 23-DOF
    RightShoulderPitch = 22
    RightShoulderRoll = 23
    RightShoulderYaw = 24
    RightElbow = 25
    RightWristRoll = 26         # == 23-DOF "elbow_roll"
    RightWristPitch = 27        # INVALID for 23-DOF
    RightWristYaw = 28          # INVALID for 23-DOF
    ArmSdkWeight = 29           # weight-blend bit (0..1)


# 23-DOF IDL index (our PKL column) -> 29-slot DDS motor array index
IDL_TO_DDS: dict[int, int] = {
    12: G1JointIndex.WaistYaw,
    13: G1JointIndex.LeftShoulderPitch,
    14: G1JointIndex.LeftShoulderRoll,
    15: G1JointIndex.LeftShoulderYaw,
    16: G1JointIndex.LeftElbow,
    17: G1JointIndex.LeftWristRoll,
    18: G1JointIndex.RightShoulderPitch,
    19: G1JointIndex.RightShoulderRoll,
    20: G1JointIndex.RightShoulderYaw,
    21: G1JointIndex.RightElbow,
    22: G1JointIndex.RightWristRoll,
}
_IDL_COLS = list(IDL_TO_DDS.keys())   # [12, 13, ..., 22]  length 11
_DDS_SLOTS = list(IDL_TO_DDS.values())  # [12, 15, 16, ..., 26]


# ---------------------------------------------------------------------------
# No-fall controller
# ---------------------------------------------------------------------------

@dataclass
class ControllerConfig:
    control_dt: float = 0.02          # 50 Hz arm-SDK publish rate (matches Unitree example)
    engage_sec: float = 1.5           # weight 0->1 + ease-in to first PKL frame
    release_sec: float = 1.0          # weight 1->0 handoff back to OEM loco
    ease_out_sec: float = 1.5         # last-frame -> snapshot neutral
    kp: float = 60.0                  # exact Unitree arm7 example gain
    kd: float = 1.5                   # exact Unitree arm7 example gain
    max_joint_vel_rad_s: float = 2.0  # inter-step velocity clamp (safety)
    tracking_abort_rad: float = 0.8   # if |q_cmd - q_meas| ever exceeds -> release


class G1NoFallController:
    """High-level wrapper that never turns off the OEM balance controller."""

    def __init__(self, iface: str, config: ControllerConfig | None = None):
        self.cfg = config or ControllerConfig()
        ChannelFactoryInitialize(0, iface)

        # Tier 1 - LocoClient (legs + balance + some gestures)
        self._loco = LocoClient()
        self._loco.SetTimeout(10.0)
        self._loco.Init()

        # Tier 2 - Canned arm gestures
        self._arm_action = G1ArmActionClient()
        self._arm_action.SetTimeout(10.0)
        self._arm_action.Init()

        # Tier 3 - Custom arm PKL overlay via rt/arm_sdk
        self._arm_pub = ChannelPublisher("rt/arm_sdk", LowCmd_)
        self._arm_pub.Init()
        self._state_sub = ChannelSubscriber("rt/lowstate", LowState_)
        self._state_sub.Init(self._on_lowstate, 10)

        self._low_cmd: LowCmd_ = unitree_hg_msg_dds__LowCmd_()
        self._low_state: Optional[LowState_] = None
        self._crc = CRC()

        self._wait_for_state(timeout=3.0)

    # ---- Tier 1: LocoClient wrappers (CANNOT fall) --------------------

    def stand(self, low: bool = False) -> None:
        if low:
            self._loco.LowStand()
        else:
            self._loco.HighStand()

    def walk(
        self,
        vx: float = 0.0,
        vy: float = 0.0,
        yaw: float = 0.0,
        duration: float = 1.0,
    ) -> None:
        """Repeated Move() at 10 Hz for `duration` seconds, then zero velocity.

        Robot self-balances throughout. No PKL, no joint arrays. Unitree
        handles CoM, ZMP, foot placement, perturbation rejection.
        """
        rate_hz = 10.0
        n = max(1, int(duration * rate_hz))
        dt = duration / n
        for _ in range(n):
            self._loco.Move(vx, vy, yaw)
            time.sleep(dt)
        self._loco.Move(0.0, 0.0, 0.0)

    def damp(self) -> None:
        self._loco.Damp()

    def zero_torque(self) -> None:
        self._loco.ZeroTorque()

    def squat_to_stand(self) -> None:
        self._loco.Damp()
        time.sleep(0.5)
        self._loco.Squat2StandUp()

    def lie_to_stand(self) -> None:
        """Get-up from lying flat (face up) on hard, flat, rough ground.

        Warning from Unitree: the ground MUST be hard, flat, and rough.
        On slippery or soft surfaces this can fail. Use only with gantry.
        """
        self._loco.Damp()
        time.sleep(0.5)
        self._loco.Lie2StandUp()

    def loco_wave(self, turn: bool = False) -> None:
        """Unitree's built-in wave hand. Body keeps balancing."""
        self._loco.WaveHand(turn)

    def loco_shake_hand(self) -> None:
        self._loco.ShakeHand()

    # ---- Tier 2: Canned G1ArmActionClient gestures (CANNOT fall) ------

    def canned_gesture(self, name: str, hold_seconds: float = 2.0) -> None:
        """Execute a preset Unitree arm gesture while legs stay balanced.

        Valid names (from unitree_sdk2py action_map):
            "release arm", "shake hand", "high five", "hug", "high wave",
            "clap", "face wave", "left kiss", "heart", "right heart",
            "hands up", "x-ray", "right hand up", "reject", "right kiss",
            "two-hand kiss"
        """
        action_id = action_map.get(name)
        if action_id is None:
            raise ValueError(
                f"Unknown canned gesture '{name}'. Valid: {list(action_map.keys())}"
            )
        self._arm_action.ExecuteAction(action_id)
        if hold_seconds > 0:
            time.sleep(hold_seconds)
            release_id = action_map.get("release arm")
            if release_id is not None:
                self._arm_action.ExecuteAction(release_id)

    # ---- Tier 3: Custom PKL arm gesture via rt/arm_sdk ----------------

    def play_arm_gesture(
        self,
        pkl_path: str | Path,
        flip_r_shoulder_roll: bool = False,
        include_waist_yaw: bool = False,
    ) -> None:
        """Stream a hero PKL's arm joints onto the robot while legs self-balance.

        Phases (legs are under OEM loco control throughout):
            A. Snapshot current measured arm pose
            B. Engage: weight 0 -> 1 and interpolate measured -> first PKL frame
            C. Stream: PKL frames at 50 Hz with per-step velocity clamping
            D. Ease-out: last PKL frame -> snapshot neutral
            E. Release: weight 1 -> 0 (smooth handoff)

        Safety:
            - Tracking abort: if |q_cmd - q_meas| exceeds tracking_abort_rad
              on any joint, immediately drop weight to 0 and raise.
            - Velocity clamp: per-step dq is clipped to max_joint_vel * dt.
            - Waist motion is OFF by default (include_waist_yaw=False).
              OEM loco uses waist_yaw for angular momentum; fighting it
              destabilizes. Only enable if you have a hero PKL that needs it.
        """
        ja, fps = self._load_pkl(pkl_path)
        q_target = ja[:, _IDL_COLS].astype(np.float32).copy()  # (N, 11)

        if flip_r_shoulder_roll:
            q_target[:, _IDL_COLS.index(19)] *= -1.0

        if not include_waist_yaw:
            q_target[:, _IDL_COLS.index(12)] = 0.0  # will be blended to snapshot

        q_snapshot = self._snapshot_measured_arm()

        if not include_waist_yaw:
            q_target[:, _IDL_COLS.index(12)] = q_snapshot[_IDL_COLS.index(12)]

        self._ramp_engage(q_snapshot, q_target[0], self.cfg.engage_sec)
        self._stream_frames(q_target, fps)
        self._ramp_segment(q_target[-1], q_snapshot, self.cfg.ease_out_sec, weight=1.0)
        self._ramp_release(q_snapshot, self.cfg.release_sec)

    # ---- Internals ----------------------------------------------------

    def _on_lowstate(self, msg: LowState_) -> None:
        self._low_state = msg

    def _wait_for_state(self, timeout: float) -> None:
        t0 = time.time()
        while self._low_state is None:
            if time.time() - t0 > timeout:
                raise RuntimeError("No rt/lowstate received - check network/peer.")
            time.sleep(0.05)

    def _snapshot_measured_arm(self) -> np.ndarray:
        q = np.zeros(len(_DDS_SLOTS), dtype=np.float32)
        for i, dds_idx in enumerate(_DDS_SLOTS):
            q[i] = self._low_state.motor_state[dds_idx].q
        return q

    def _write(self, q_vec: np.ndarray, weight: float) -> None:
        weight = float(np.clip(weight, 0.0, 1.0))

        q_meas = self._snapshot_measured_arm()
        err = np.abs(q_vec - q_meas)
        if np.max(err) > self.cfg.tracking_abort_rad:
            j = int(np.argmax(err))
            self._emergency_release()
            raise RuntimeError(
                f"Tracking error {err[j]:.2f} rad on arm-joint {_IDL_COLS[j]} "
                f"> limit {self.cfg.tracking_abort_rad:.2f} rad. arm_sdk released."
            )

        self._low_cmd.motor_cmd[G1JointIndex.ArmSdkWeight].q = weight

        for i, dds_idx in enumerate(_DDS_SLOTS):
            mc = self._low_cmd.motor_cmd[dds_idx]
            mc.q = float(q_vec[i])
            mc.dq = 0.0
            mc.tau = 0.0
            mc.kp = self.cfg.kp
            mc.kd = self.cfg.kd

        self._low_cmd.crc = self._crc.Crc(self._low_cmd)
        self._arm_pub.Write(self._low_cmd)

    def _emergency_release(self) -> None:
        self._low_cmd.motor_cmd[G1JointIndex.ArmSdkWeight].q = 0.0
        self._low_cmd.crc = self._crc.Crc(self._low_cmd)
        self._arm_pub.Write(self._low_cmd)

    def _ramp_engage(self, q_from: np.ndarray, q_to: np.ndarray, seconds: float) -> None:
        n = max(2, int(seconds / self.cfg.control_dt))
        t0 = time.time()
        prev = q_from.copy()
        for i in range(n):
            alpha = (i + 1) / n
            q = (1.0 - alpha) * q_from + alpha * q_to
            q = self._clamp_step(prev, q)
            self._write(q, weight=alpha)
            prev = q
            self._sleep_to(t0 + (i + 1) * self.cfg.control_dt)

    def _ramp_segment(
        self, q_from: np.ndarray, q_to: np.ndarray, seconds: float, weight: float
    ) -> None:
        n = max(2, int(seconds / self.cfg.control_dt))
        t0 = time.time()
        prev = q_from.copy()
        for i in range(n):
            alpha = (i + 1) / n
            q = (1.0 - alpha) * q_from + alpha * q_to
            q = self._clamp_step(prev, q)
            self._write(q, weight=weight)
            prev = q
            self._sleep_to(t0 + (i + 1) * self.cfg.control_dt)

    def _ramp_release(self, q_hold: np.ndarray, seconds: float) -> None:
        n = max(2, int(seconds / self.cfg.control_dt))
        t0 = time.time()
        for i in range(n):
            alpha = (i + 1) / n
            self._write(q_hold, weight=1.0 - alpha)
            self._sleep_to(t0 + (i + 1) * self.cfg.control_dt)
        self._emergency_release()  # explicit final weight=0

    def _stream_frames(self, q_target: np.ndarray, fps: float) -> None:
        n_frames = q_target.shape[0]
        duration = n_frames / float(fps)
        ctrl_hz = 1.0 / self.cfg.control_dt
        n_steps = int(duration * ctrl_hz)
        t0 = time.time()
        prev = q_target[0].copy()
        for i in range(n_steps):
            t = i / ctrl_hz
            f = t * fps
            f0 = int(np.floor(f))
            f1 = min(f0 + 1, n_frames - 1)
            alpha = f - f0
            q = (1.0 - alpha) * q_target[f0] + alpha * q_target[f1]
            q = self._clamp_step(prev, q)
            self._write(q, weight=1.0)
            prev = q
            self._sleep_to(t0 + (i + 1) * self.cfg.control_dt)

    def _clamp_step(self, q_prev: np.ndarray, q_target: np.ndarray) -> np.ndarray:
        max_step = self.cfg.max_joint_vel_rad_s * self.cfg.control_dt
        dq = np.clip(q_target - q_prev, -max_step, max_step)
        return q_prev + dq

    @staticmethod
    def _sleep_to(t_target: float) -> None:
        delay = t_target - time.time()
        if delay > 0:
            time.sleep(delay)

    @staticmethod
    def _load_pkl(path: str | Path) -> tuple[np.ndarray, float]:
        with open(path, "rb") as f:
            d = pickle.load(f)
        ja = np.asarray(d["joint_angles"])
        if ja.ndim != 2 or ja.shape[1] < 23:
            raise ValueError(
                f"Bad PKL {path}: joint_angles shape {ja.shape}, expected (N, >=23)"
            )
        fps = float(d.get("fps", 30.0))
        return ja, fps


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

_MENU = """
IMPORTANT STARTUP ORDER:
    On fresh boot the robot is in damping / squat / lying state.
    HighStand / Move / canned-gesture / play commands will FAIL until you
    first run one of the getting-up sequences below:

        squat2stand   -> if robot is crouched (typical on gantry)
        lie2stand     -> if robot is lying flat face-up on hard ground

    After the robot is standing, the rest of the menu works.

Commands (robot self-balances throughout — it will not fall):
    damp                       Damping (passive hold) — always safe
    squat2stand                Damp -> Squat2StandUp (RUN FIRST on gantry)
    lie2stand                  Damp -> Lie2StandUp (from flat floor only)
    stand                      HighStand (requires robot already standing)
    low                        LowStand
    fwd [m/s] [sec]            Move forward   (default 0.2 m/s, 2 s)
    back [m/s] [sec]           Move backward
    left [m/s] [sec]           Side-step left
    right [m/s] [sec]          Side-step right
    turn [rad/s] [sec]         Rotate in place
    zero                       Zero torque (motors OFF)
    loco_wave [turn]           Built-in wave hand
    canned NAME                Canned arm gesture (use `list` to see names)
    play PATH                  Play hero PKL on arms only (rt/arm_sdk overlay)
    list                       List canned gesture names
    help                       Show this menu
    quit                       Exit
"""


def _interactive(ctrl: G1NoFallController, flip_r: bool) -> None:
    print(_MENU)
    while True:
        try:
            raw = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not raw:
            continue
        parts = raw.split()
        op = parts[0].lower()
        try:
            if op == "quit":
                break
            elif op == "help":
                print(_MENU)
            elif op == "list":
                for name in action_map.keys():
                    print(f"  - {name}")
            elif op == "stand":
                ctrl.stand()
            elif op == "low":
                ctrl.stand(low=True)
            elif op in ("fwd", "back", "left", "right", "turn"):
                v = float(parts[1]) if len(parts) > 1 else (0.3 if op == "turn" else 0.2)
                dur = float(parts[2]) if len(parts) > 2 else 2.0
                kwargs = {"fwd": {"vx": v}, "back": {"vx": -v},
                          "left": {"vy": v}, "right": {"vy": -v},
                          "turn": {"yaw": v}}[op]
                ctrl.walk(duration=dur, **kwargs)
            elif op == "damp":
                ctrl.damp()
            elif op == "zero":
                ctrl.zero_torque()
            elif op == "squat2stand":
                ctrl.squat_to_stand()
            elif op == "lie2stand":
                ctrl.lie_to_stand()
            elif op == "loco_wave":
                ctrl.loco_wave(turn=(len(parts) > 1 and parts[1] == "turn"))
            elif op == "canned":
                if len(parts) < 2:
                    print("usage: canned <name>  (type `list` for names)")
                    continue
                name = " ".join(parts[1:])
                ctrl.canned_gesture(name)
            elif op == "play":
                if len(parts) < 2:
                    print("usage: play <pkl_path>")
                    continue
                ctrl.play_arm_gesture(parts[1], flip_r_shoulder_roll=flip_r)
            else:
                print(f"unknown command: {op}   (type `help`)")
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}")


def main() -> None:
    p = argparse.ArgumentParser(description="No-fall G1 controller (rt/arm_sdk overlay).")
    p.add_argument("iface", help="network interface, e.g. enp0s31f6 (Linux) or en0")
    p.add_argument("--pkl", default=None, help="one-shot: play this hero PKL and exit")
    p.add_argument("--flip-r-shoulder-roll", action="store_true",
                   help="negate R_shoulder_roll column (under investigation; see _kpop/ logs)")
    p.add_argument("--no-confirm", action="store_true",
                   help="skip the 'press enter' safety prompt")
    args = p.parse_args()

    if not args.no_confirm:
        print("WARNING: Ensure gantry is attached, floor is clear, "
              "L1+L2 e-stop is ready. Robot in DAMPING mode (L2+B).")
        input("Press Enter to initialize the controller...")

    ctrl = G1NoFallController(args.iface)
    print("[ok] LocoClient + G1ArmActionClient + rt/arm_sdk publisher initialized.")
    print("[ok] OEM locomotion stabilizer is ACTIVE. Robot will self-balance.")

    if args.pkl:
        print("[play] Damp -> Squat2StandUp -> HighStand sequence...")
        ctrl.squat_to_stand()
        time.sleep(2.5)
        ctrl.stand()
        time.sleep(1.5)
        print(f"[play] Playing arm gesture from {args.pkl}")
        ctrl.play_arm_gesture(args.pkl, flip_r_shoulder_roll=args.flip_r_shoulder_roll)
        print("[play] Done. Damping.")
        ctrl.damp()
        return

    _interactive(ctrl, flip_r=args.flip_r_shoulder_roll)


if __name__ == "__main__":
    sys.exit(main())
