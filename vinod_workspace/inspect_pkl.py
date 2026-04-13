"""
inspect_pkl.py — Show which joint indices are active in a pkl file.
Tells you whether the pkl is in 29-DOF or 23-DOF (remapped) layout.

Usage:
    python3 vinod_workspace/inspect_pkl.py --pkl kim_workspace/movements/hulk_smash_kinematics.pkl
"""
import argparse
import pickle
import numpy as np

NAMES_29DOF = [
    # legs 0-11
    "L_hip_pitch","L_hip_roll","L_hip_yaw","L_knee","L_ankle_pitch","L_ankle_roll",
    "R_hip_pitch","R_hip_roll","R_hip_yaw","R_knee","R_ankle_pitch","R_ankle_roll",
    # waist 12-14
    "waist_yaw","waist_roll","waist_pitch",
    # left arm 15-21
    "L_shoulder_pitch","L_shoulder_roll","L_shoulder_yaw","L_elbow",
    "L_wrist_roll","L_wrist_pitch","L_wrist_yaw",
    # right arm 22-28
    "R_shoulder_pitch","R_shoulder_roll","R_shoulder_yaw","R_elbow",
    "R_wrist_roll","R_wrist_pitch","R_wrist_yaw",
    # extended 29-34
    "ext_29","ext_30","ext_31","ext_32","ext_33","ext_34",
]

NAMES_23DOF = [
    # legs 0-11
    "L_hip_pitch","L_hip_roll","L_hip_yaw","L_knee","L_ankle_pitch","L_ankle_roll",
    "R_hip_pitch","R_hip_roll","R_hip_yaw","R_knee","R_ankle_pitch","R_ankle_roll",
    # waist 12
    "TORSO",
    # left arm 13-17
    "L_shoulder_pitch","L_shoulder_roll","L_shoulder_yaw","L_elbow_pitch","L_elbow_roll",
    # right arm 18-22
    "R_shoulder_pitch","R_shoulder_roll","R_shoulder_yaw","R_elbow_pitch","R_elbow_roll",
    # unused 23-34
    "unused_23","unused_24","unused_25","unused_26","unused_27","unused_28",
    "unused_29","unused_30","unused_31","unused_32","unused_33","unused_34",
]

parser = argparse.ArgumentParser()
parser.add_argument("--pkl", required=True)
args = parser.parse_args()

with open(args.pkl, "rb") as f:
    data = pickle.load(f)

joints = np.array(data["joint_angles"], dtype=np.float32)
print(f"Shape: {joints.shape}  ({joints.shape[0]} frames x {joints.shape[1]} DOF)")
print(f"FPS: {data.get('fps', 'N/A')}")
print()

THRESHOLD = 0.01  # rad — ignore near-zero joints
print(f"{'Idx':<5} {'Max|val|':>10}  {'Range':>20}  29-DOF name → 23-DOF name")
print("-" * 75)
for i in range(joints.shape[1]):
    col = joints[:, i]
    maxval = float(np.max(np.abs(col)))
    if maxval < THRESHOLD:
        continue
    lo, hi = float(col.min()), float(col.max())
    n29 = NAMES_29DOF[i] if i < len(NAMES_29DOF) else f"idx_{i}"
    n23 = NAMES_23DOF[i] if i < len(NAMES_23DOF) else f"idx_{i}"
    print(f"{i:<5} {maxval:>10.4f}  [{lo:>8.4f}, {hi:>8.4f}]  {n29} → {n23}")

print()
# Decide layout
arm_29 = np.max(np.abs(joints[:, 15:29]))  # non-zero if 29-DOF layout
arm_23 = np.max(np.abs(joints[:, 13:18]))  # non-zero if 23-DOF layout (left arm)

if arm_29 > THRESHOLD and arm_23 < THRESHOLD:
    print("VERDICT: PKL is in 29-DOF layout  → deploy_real.py ARM_JOINTS should be range(15, 29)")
elif arm_23 > THRESHOLD and arm_29 < THRESHOLD:
    print("VERDICT: PKL is in 23-DOF (remapped) layout  → deploy_real.py ARM_JOINTS should be range(13, 23)")
elif arm_23 > THRESHOLD and arm_29 > THRESHOLD:
    print("VERDICT: AMBIGUOUS — active joints in both 13-17 and 15-28 ranges.")
    print("         Check the index list above — if 13/14 are active, it's 23-DOF remapped.")
else:
    print("VERDICT: No arm motion detected in this pkl.")
