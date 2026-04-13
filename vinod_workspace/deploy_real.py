"""
deploy_real.py — 500 Hz PD Control Kinematic Playback (Hardware Deployment)
----------------------------------------------------------------------------
This script completely bypasses the Isaac Lab Sim-to-Real RL policy.
It executes raw `.pkl` kinematic trajectories directly on the Unitree G1 
using aggressive 500Hz PD control with safety velocity clamps.

SAFETY PRECONDITIONS (do not skip):
  1. Robot is physically cleared of obstacles. (Gantry suspension recommended for first test).
  2. Robot was booted in DAMPING mode (L2+B), taken to zero-torque manually.
  3. Operator holds physical L1+L2 E-Stop.

Features:
- Reads initial encoder state and automatically interpolates (EASES) over 3 seconds 
  into the first frame of the `.pkl` array to prevent violent torque snaps.
- Automatically isolates 0-14 (legs/waist) with rigid support gains (Kp=200)
  and 15-28 (arms) with softer dynamic gains (Kp=60).
- Strict Velocity Clamp: If ANY joint exceeds 10 rad/s, instantly kills all motor torque.

Usage:
    python deploy_real.py --pkl output/hulk_kinematics.pkl --iface eth0
"""

import os
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
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient

NUM_MOTOR = 35

# Joint topology — G1 23-DOF hardware IDL
# PKL format (after remap_23dof.py): 0-11 legs, 12 TORSO, 13-17 L_arm, 18-22 R_arm
LEG_JOINTS   = list(range(0, 12))    # 0-11:  legs
WAIST_JOINTS = [12]                  # 12:    TORSO (waist_yaw only on 23-DOF)
ARM_JOINTS   = list(range(13, 23))   # 13-17: L_arm, 18-22: R_arm
EXT_JOINTS   = list(range(23, 35))   # 23-34: unused on 23-DOF

# DUAL-TIER PD GAINS 
# Legs/Waist need massive rigidity to support gravity CoM
KP_LEG, KD_LEG = 200.0, 10.0
KP_WAIST, KD_WAIST = 200.0, 10.0
# Arms need fluid compliance to execute the hero pose gracefully without jitter
KP_ARM, KD_ARM = 60.0, 5.0
# Extended joints disabled
KP_EXT, KD_EXT = 0.0, 0.0

# 10 rad/sec hard abort limit to save the hardware gears
VELOCITY_ABORT_THRESHOLD = 10.0  

CTRL_HZ = 500.0
CTRL_DT = 1.0 / CTRL_HZ
PKL_FPS = 30.0
EASE_IN_SECONDS = 3.0


def _make_cmd(mode_pr: int = 0, mode_machine: int = 0) -> LowCmd_:
    """Initialize base structure for 35 motors once."""
    cmd = LowCmd_default()
    cmd.mode_pr = mode_pr
    cmd.mode_machine = mode_machine
    for i in range(NUM_MOTOR):
        cmd.motor_cmd[i].mode = 0x01  # PMSM Control Mode
        cmd.motor_cmd[i].q   = 0.0
        cmd.motor_cmd[i].kp  = 0.0
        cmd.motor_cmd[i].dq  = 0.0
        cmd.motor_cmd[i].kd  = 0.0
        cmd.motor_cmd[i].tau = 0.0
    return cmd

def _build_gain_map():
    gains = {}
    for i in range(NUM_MOTOR):
        if i in LEG_JOINTS:
            gains[i] = (KP_LEG, KD_LEG)
        elif i in WAIST_JOINTS:
            gains[i] = (KP_WAIST, KD_WAIST)
        elif i in ARM_JOINTS:
            gains[i] = (KP_ARM, KD_ARM)
        else:
            gains[i] = (KP_EXT, KD_EXT)
    return gains


class RealDeployController:
    def __init__(self, pkl_frames: np.ndarray, speed_factor: float):
        self.frames = pkl_frames
        self.speed_factor = speed_factor
        self.current_state: LowState_ | None = None
        self.aborted = False
        self._mode_machine: int | None = None  # read from robot on first LowState

        self.num_frames = len(pkl_frames)
        # Using floating point index interpolation at 500Hz
        self.active_fps = PKL_FPS * speed_factor

        self._cmd = _make_cmd()
        self._zero_cmd = _make_cmd()
        self._gains = _build_gain_map()
        self._crc = CRC()

        # Load gains into cmd reference
        for i in range(NUM_MOTOR):
            kp, kd = self._gains[i]
            self._cmd.motor_cmd[i].kp = kp
            self._cmd.motor_cmd[i].kd = kd

    def on_low_state(self, msg: LowState_):
        self.current_state = msg
        # Capture mode_machine from robot on first message and echo it in every cmd.
        # The robot silently ignores LowCmd whose mode_machine doesn't match its own.
        if self._mode_machine is None:
            self._mode_machine = msg.mode_machine
            self._cmd.mode_machine = self._mode_machine
            self._zero_cmd.mode_machine = self._mode_machine
            print(f"[DDS] mode_machine={self._mode_machine} captured from robot")

    def _check_safety_abort(self, msg: LowState_) -> bool:
        for i in LEG_JOINTS + WAIST_JOINTS + ARM_JOINTS:
            dq = abs(msg.motor_state[i].dq)
            if dq > VELOCITY_ABORT_THRESHOLD:
                print(f"\\n[CRITICAL ABORT] Joint {i} triggered Velocity Clamp ({dq:.2f} rad/s). Engaging Limp Mode!")
                return True
        return False

    def ease_to_stand(self, publisher: ChannelPublisher):
        """Linearly interpolates from whatever crumpled mass the robot is currently in natively, to the very first frame of the PKL"""
        print(f"\\n[PHASE 1] Easing to first frame over {EASE_IN_SECONDS} seconds...")
        start_q = np.array([self.current_state.motor_state[i].q for i in range(NUM_MOTOR)])
        target_q = self.frames[0]
        
        ease_ticks = int(EASE_IN_SECONDS * CTRL_HZ)
        for tick in range(ease_ticks):
            loop_start = time.monotonic()
            
            if self._check_safety_abort(self.current_state):
                self.aborted = True
                return

            alpha = tick / float(ease_ticks)
            interp_q = (1.0 - alpha) * start_q + alpha * target_q
            
            for i in range(NUM_MOTOR):
                if i in LEG_JOINTS + WAIST_JOINTS + ARM_JOINTS:
                    self._cmd.motor_cmd[i].q = float(interp_q[i])
                    
            self._cmd.crc = self._crc.Crc(self._cmd)
            publisher.Write(self._cmd)

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0, CTRL_DT - elapsed))

    def run(self, publisher: ChannelPublisher):
        if self.current_state is None:
            print("Awaiting DDS bridge connection...")
            while self.current_state is None:
                time.sleep(0.1)

        print("\\nDDS Bridge Live! Starting deployment safely sequence...")
        
        # PHASE 1: EASE IN
        self.ease_to_stand(publisher)
        if self.aborted:
            self._kill(publisher)
            return
            
        print("\\n[PHASE 2] Executing Kinematic Payload")
        
        # PHASE 2: ACTIVE PLAYBACK
        start_time = time.monotonic()
        while not self.aborted:
            loop_start = time.monotonic()
            
            if self._check_safety_abort(self.current_state):
                self.aborted = True
                break

            # Float interpolation over time to match 500Hz cleanly
            t = loop_start - start_time
            float_idx = t * self.active_fps
            
            if float_idx >= self.num_frames - 1:
                break # Sequence finished
                
            idx0 = int(float_idx)
            idx1 = idx0 + 1
            alpha = float_idx - idx0
            
            interp_q = (1.0 - alpha) * self.frames[idx0] + alpha * self.frames[idx1]
            
            for i in range(NUM_MOTOR):
                if i in LEG_JOINTS + WAIST_JOINTS + ARM_JOINTS:
                    self._cmd.motor_cmd[i].q = float(interp_q[i])
                    
            self._cmd.crc = self._crc.Crc(self._cmd)
            publisher.Write(self._cmd)

            # Diagnostic telemetry formatting
            if int(t * CTRL_HZ) % (int(CTRL_HZ // 5)) == 0:
                print(f"Playback: Frame {float_idx:.1f}/{self.num_frames} | Velocity clamps holding...", end="\\r")
                
            elapsed = time.monotonic() - loop_start
            time.sleep(max(0, CTRL_DT - elapsed))
            
        self._kill(publisher)

    def _kill(self, publisher: ChannelPublisher):
        print("\\n\\n[DISENGAGE] Dropping into zero-torque limp compliance...")
        for _ in range(15):
            self._zero_cmd.crc = self._crc.Crc(self._zero_cmd)
            publisher.Write(self._zero_cmd)
            time.sleep(0.01)
        print("Robot is safe to handle.")


def main():
    parser = argparse.ArgumentParser(description="Full-Body 500Hz PD Kinematic Deployment")
    parser.add_argument("--pkl", required=True, help="Path to .pkl array file")
    parser.add_argument("--iface", default="enp0s31f6", help="Network interface (default: enp0s31f6 for iotlab Linux)")
    parser.add_argument("--domain", type=int, default=0, help="DDS Domain ID (default: 0 for real G1)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier (0.5 = half speed)")
    parser.add_argument("--peer", default="", help="Robot IP for unicast DDS peer discovery (e.g. 192.168.123.164). Required for real hardware.")
    args = parser.parse_args()

    print("=" * 60)
    print("VLAW FALLBACK: PHYSICAL KINEMATIC DEPLOYMENT")
    print("=" * 60)

    try:
        with open(args.pkl, "rb") as f:
            frames = pickle.load(f)["joint_angles"]
    except Exception as e:
        print(f"Failed to load pkl: {e}")
        sys.exit(1)

    print(f"Payload target acquired: {len(frames)} frames.")

    if args.peer:
        os.environ["CYCLONEDDS_URI"] = (
            f"<CycloneDDS><Domain><Discovery><Peers>"
            f"<Peer address=\"{args.peer}\"/>"
            f"</Peers></Discovery></Domain></CycloneDDS>"
        )
        print(f"CYCLONEDDS_URI set for peer {args.peer}")

    ChannelFactoryInitialize(args.domain, args.iface)

    # Release any active high-level locomotion mode (balance, walk, etc.).
    # Without this the built-in controller overrides all low-level PD commands.
    print("Releasing active motion mode...")
    msc = MotionSwitcherClient()
    msc.SetTimeout(5.0)
    msc.Init()
    status, result = msc.CheckMode()
    while result.get("name"):
        print(f"  Active mode: {result['name']} — releasing...")
        msc.ReleaseMode()
        time.sleep(1)
        status, result = msc.CheckMode()
    print("Motion mode released. Proceeding to low-level control.")

    controller = RealDeployController(frames, args.speed)
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(controller.on_low_state, 10)
    pub = ChannelPublisher("rt/lowcmd", LowCmd_)
    pub.Init()

    try:
        controller.run(pub)
    except KeyboardInterrupt:
        controller.aborted = True
        controller._kill(pub)

if __name__ == "__main__":
    main()
