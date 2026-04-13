"""
G1 Encoder Monitor — Step 2: Zero-Torque Encoder Readback Test
---------------------------------------------------------------
READ ONLY. No commands are published to the robot.

Boot the G1 in DAMPING mode (L2+B on controller). Then run this script.
Physically manipulate each joint by hand. Verify that the terminal output
reflects the angle change in the correct motor index.

This script falsifies the assumption that CycloneDDS is correctly bridged
and that joint indices 0-34 map as expected.

Usage:
    # For real hardware (Ethernet, robot at 192.168.123.x):
    python g1_encoder_monitor.py --interface eth0

    # For MuJoCo simulation bridge (loopback):
    python g1_encoder_monitor.py --interface lo

Requirements:
    - CycloneDDS installed and CYCLONEDDS_HOME set
    - unitree_sdk2_python installed (pip install -e .)
    - Robot in DAMPING mode OR unitree_mujoco simulation running
"""

import sys
import time
import argparse

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_

# G1 hardware has 35 motor channels via unitree_hg IDL
NUM_MOTOR = 35

# Joint names indexed by hardware motor ID (0-34)
# Source: CLAUDE.md + unitree_hg IDL ordering
# NOTE: Joints 29-34 are wrist/hand extensions not in the 29-DOF CLAUDE.md map.
#       Their exact mapping must be confirmed during zero-torque manipulation test.
JOINT_NAMES = [
    # Left leg (0-5)
    "L_hip_pitch", "L_hip_roll", "L_hip_yaw",
    "L_knee",
    "L_ankle_pitch", "L_ankle_roll",
    # Right leg (6-11)
    "R_hip_pitch", "R_hip_roll", "R_hip_yaw",
    "R_knee",
    "R_ankle_pitch", "R_ankle_roll",
    # Waist (12-14)
    "waist_yaw", "waist_roll", "waist_pitch",
    # Left arm (15-21)
    "L_shoulder_pitch", "L_shoulder_roll", "L_shoulder_yaw",
    "L_elbow",
    "L_wrist_roll", "L_wrist_pitch", "L_wrist_yaw",
    # Right arm (22-28)
    "R_shoulder_pitch", "R_shoulder_roll", "R_shoulder_yaw",
    "R_elbow",
    "R_wrist_roll", "R_wrist_pitch", "R_wrist_yaw",
    # Extended wrist/hand joints (29-34) — confirm by manipulation
    "ext_29", "ext_30", "ext_31", "ext_32", "ext_33", "ext_34",
]

# Print update interval in seconds
PRINT_HZ = 10.0


class EncoderMonitor:
    def __init__(self):
        self.latest_state: LowState_ | None = None
        self.last_print = 0.0

    def on_low_state(self, msg: LowState_):
        self.latest_state = msg
        now = time.monotonic()
        if now - self.last_print >= 1.0 / PRINT_HZ:
            self.last_print = now
            self._print_state(msg)

    def _print_state(self, msg: LowState_):
        # Clear terminal line by line for readability
        print("\033[2J\033[H", end="")  # clear screen + move cursor home
        print("=" * 60)
        print("G1 Encoder Monitor  (Ctrl+C to exit)")
        print("=" * 60)

        imu = msg.imu_state
        print(f"IMU  quat  w={imu.quaternion[0]:.3f} x={imu.quaternion[1]:.3f} "
              f"y={imu.quaternion[2]:.3f} z={imu.quaternion[3]:.3f}")
        print(f"IMU  gyro  x={imu.gyroscope[0]:.3f} y={imu.gyroscope[1]:.3f} "
              f"z={imu.gyroscope[2]:.3f} rad/s")
        print(f"IMU  accel x={imu.accelerometer[0]:.3f} y={imu.accelerometer[1]:.3f} "
              f"z={imu.accelerometer[2]:.3f} m/s²")
        print("-" * 60)
        print(f"{'ID':<4} {'Name':<22} {'q (rad)':>10} {'dq (rad/s)':>12} {'tau (Nm)':>10}")
        print("-" * 60)

        for i in range(NUM_MOTOR):
            mc = msg.motor_state[i]
            name = JOINT_NAMES[i] if i < len(JOINT_NAMES) else f"motor_{i}"
            print(f"{i:<4} {name:<22} {mc.q:>10.4f} {mc.dq:>12.4f} {mc.tau_est:>10.3f}")

        print("=" * 60)
        print("Physically manipulate joints by hand.")
        print("Confirm: which motor index responds to which limb?")
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="G1 Encoder Monitor — read-only DDS subscriber")
    parser.add_argument("--interface", default="lo",
                        help="Network interface: 'lo' for simulation, 'eth0' for real hardware")
    parser.add_argument("--domain", type=int, default=1, help="DDS Domain ID (default: 1)")
    args = parser.parse_args()

    print(f"Initializing CycloneDDS on interface '{args.interface}', domain {args.domain}...")
    ChannelFactoryInitialize(args.domain, args.interface)

    monitor = EncoderMonitor()

    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(monitor.on_low_state, 10)

    print("Subscribed to rt/lowstate. Waiting for G1 state messages...")
    print("If nothing appears within 5 seconds, CycloneDDS is not bridged correctly.")
    print("Check: is the robot powered on? Is CYCLONEDDS_HOME set? Ping 192.168.123.x?")
    print()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


if __name__ == "__main__":
    main()
