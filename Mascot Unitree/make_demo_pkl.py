"""
make_demo_pkl.py — Generate a synthetic robot_motion.pkl for demo/testing.

Creates a Spider-Man web-shoot arm animation using real G1 joint angles.
Run: python make_demo_pkl.py
"""

import pickle
import numpy as np
from pathlib import Path

# Actuator order from g1_23dof.xml (29 actuators)
ACTUATOR_ORDER = [
    "left_hip_pitch",       # 0
    "left_hip_roll",        # 1
    "left_hip_yaw",         # 2
    "left_knee",            # 3
    "left_ankle_pitch",     # 4
    "left_ankle_roll",      # 5
    "right_hip_pitch",      # 6
    "right_hip_roll",       # 7
    "right_hip_yaw",        # 8
    "right_knee",           # 9
    "right_ankle_pitch",    # 10
    "right_ankle_roll",     # 11
    "waist_yaw",            # 12
    "waist_roll",           # 13
    "waist_pitch",          # 14
    "left_shoulder_pitch",  # 15
    "left_shoulder_roll",   # 16
    "left_shoulder_yaw",    # 17
    "left_elbow",           # 18
    "left_wrist_roll",      # 19
    "left_wrist_pitch",     # 20
    "left_wrist_yaw",       # 21
    "right_shoulder_pitch", # 22
    "right_shoulder_roll",  # 23
    "right_shoulder_yaw",   # 24
    "right_elbow",          # 25
    "right_wrist_roll",     # 26
    "right_wrist_pitch",    # 27
    "right_wrist_yaw",      # 28
]

# Stable athletic stance (legs, from STABLE_BALANCE_POSE)
STABLE_LEGS = {
    "left_hip_pitch":    -0.6,
    "right_hip_pitch":   -0.6,
    "left_knee":          1.2,
    "right_knee":         1.2,
    "left_ankle_pitch":  -0.6,
    "right_ankle_pitch": -0.6,
}

def make_frame(arm_phase: float) -> list:
    """
    arm_phase: 0.0 = arms at sides, 1.0 = web-shoot pose (right arm extended)
    """
    t = arm_phase
    pose = {}

    # Legs — locked stable
    for k, v in STABLE_LEGS.items():
        pose[k] = v

    # Waist — slight forward lean + turn toward web-shoot
    pose["waist_yaw"]   =  0.15 * np.sin(t * np.pi)
    pose["waist_pitch"] = -0.05

    # Right arm — Spider-Man web shoot: extend forward, elbow bent, wrist snap
    pose["right_shoulder_pitch"] = -1.2 * t          # swing forward
    pose["right_shoulder_roll"]  = -0.3 * t          # slight inward
    pose["right_shoulder_yaw"]   =  0.0
    pose["right_elbow"]          =  1.0 * (1 - t)    # straightens as arm extends
    pose["right_wrist_pitch"]    = -0.4 * t          # wrist snap down
    pose["right_wrist_roll"]     =  0.0

    # Left arm — counter-balance pull back
    pose["left_shoulder_pitch"]  =  0.4 * t
    pose["left_shoulder_roll"]   =  0.8 * t          # opens outward
    pose["left_shoulder_yaw"]    =  0.0
    pose["left_elbow"]           =  1.2 * t
    pose["left_wrist_pitch"]     =  0.0
    pose["left_wrist_roll"]      =  0.0

    return [pose.get(name, 0.0) for name in ACTUATOR_ORDER]


def main():
    fps = 10
    duration = 3.0  # seconds
    n_frames = int(fps * duration)

    # Ease in, hold, ease out
    phases = []
    for i in range(n_frames):
        t = i / (n_frames - 1)
        # Smooth S-curve: shoot (0→1) then retract (1→0)
        if t < 0.4:
            phase = t / 0.4                           # ramp up
        elif t < 0.65:
            phase = 1.0                               # hold web-shoot
        else:
            phase = 1.0 - (t - 0.65) / 0.35          # return
        phases.append(max(0.0, min(1.0, phase)))

    dof_pos = [make_frame(p) for p in phases]

    # Root stays fixed at standing height
    root_pos = [[0.0, 0.0, 0.793]] * n_frames
    root_rot = [[0.0, 0.0, 0.0, 1.0]] * n_frames  # [qx,qy,qz,qw]

    trajectory = {
        "dof_pos":  dof_pos,
        "root_pos": root_pos,
        "root_rot": root_rot,
        "fps":      fps,
    }

    out = Path("output/spiderman_webshoot.pkl")
    out.parent.mkdir(exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(trajectory, f)
    print(f"✅ Saved {n_frames} frames → {out}")
    print(f"   Keys: {list(trajectory.keys())}")


if __name__ == "__main__":
    main()
