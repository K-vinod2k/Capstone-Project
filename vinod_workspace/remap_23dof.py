"""
Remap PKL files from 29-DOF layout to 23-DOF hardware IDL layout.

29-DOF layout (what PKLs currently contain):
  0-11: legs, 12: waist_yaw, 13: waist_roll, 14: waist_pitch
  15-21: left arm (shoulder x3, elbow, wrist x3)
  22-28: right arm (shoulder x3, elbow, wrist x3)
  29-34: zeros

23-DOF hardware IDL (what the physical robot expects):
  0-11: legs, 12: TORSO (waist_yaw only)
  13: L_SHOULDER_PITCH, 14: L_SHOULDER_ROLL, 15: L_SHOULDER_YAW
  16: L_ELBOW_PITCH,    17: L_ELBOW_ROLL
  18: R_SHOULDER_PITCH, 19: R_SHOULDER_ROLL, 20: R_SHOULDER_YAW
  21: R_ELBOW_PITCH,    22: R_ELBOW_ROLL
  23-34: zeros (unused on 23-DOF)

Wrist joints (29-DOF indices 19-21, 26-28) are dropped — 23-DOF has no wrists.
23-DOF has L/R_ELBOW_PITCH + L/R_ELBOW_ROLL (2-DOF elbow);
29-DOF PKL only has 1-DOF elbow — ELBOW_ROLL is left at 0.
"""
import pickle
import numpy as np
import os

NUM_MOTOR = 35

# Source index in 29-DOF PKL → destination index in 23-DOF IDL
# Only non-trivial remappings listed (legs 0-12 stay identical)
REMAP = {
    # waist: only yaw carries over; roll(13) and pitch(14) are dropped (no 23-DOF joint)
    12: 12,  # waist_yaw → TORSO
    # left arm
    15: 13,  # L_shoulder_pitch
    16: 14,  # L_shoulder_roll
    17: 15,  # L_shoulder_yaw
    18: 16,  # L_elbow       → L_elbow_pitch (best approximation)
    # 19 L_wrist_roll  → dropped (no wrist on 23-DOF)
    # 20 L_wrist_pitch → dropped
    # 21 L_wrist_yaw   → dropped
    # right arm
    22: 18,  # R_shoulder_pitch
    23: 19,  # R_shoulder_roll
    24: 20,  # R_shoulder_yaw
    25: 21,  # R_elbow       → R_elbow_pitch
    # 26 R_wrist_roll  → dropped
    # 27 R_wrist_pitch → dropped
    # 28 R_wrist_yaw   → dropped
}


def remap_frame(row_29dof: np.ndarray) -> np.ndarray:
    """Convert one frame (35,) from 29-DOF layout to 23-DOF layout."""
    out = np.zeros(NUM_MOTOR, dtype=np.float32)
    # Legs 0-11 are identical
    out[:12] = row_29dof[:12]
    # Apply explicit remaps
    for src, dst in REMAP.items():
        out[dst] = row_29dof[src]
    return out


movements_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "kim_workspace", "movements")

for fname in sorted(os.listdir(movements_dir)):
    if not fname.endswith(".pkl"):
        continue
    path = os.path.join(movements_dir, fname)
    with open(path, "rb") as f:
        data = pickle.load(f)

    joints = np.array(data["joint_angles"], dtype=np.float32)
    remapped = np.stack([remap_frame(row) for row in joints])
    data["joint_angles"] = remapped

    with open(path, "wb") as f:
        pickle.dump(data, f)

    # Verify
    arm_active = np.max(np.abs(remapped[:, 13:23]))
    print(f"{fname:<45}  {len(joints)} frames  max_arm_val={arm_active:.3f}")

print("\nDone. PKLs remapped to 23-DOF layout.")
