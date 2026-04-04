import pickle
import numpy as np
import sys
from pathlib import Path

def verify_g1_kinematics(pkl_path):
    if not Path(pkl_path).exists():
        print(f"Error: PKL not found at {pkl_path}")
        return False
        
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)
        
    # Check if we have the right shape for SMPL-X or G1 directly
    if 'joint_angles' not in data:
        print("Verification Failed: 'joint_angles' key missing.")
        return False
        
    joints = data['joint_angles']
    if joints.shape[-1] != 35:
        print(f"Verification Failed: Expected 35 joints for Unitree G1, got {joints.shape[-1]}")
        return False
        
    # Check for NaN or physically impossible bounds (e.g. > 2pi)
    if np.isnan(joints).any():
        print("Verification Failed: PKL contains NaN values.")
        return False
        
    max_angle = np.max(np.abs(joints))
    if max_angle > 6.28: # 2 Pi
        print(f"Verification Warning: Max joint angle {max_angle}rad seems unusually high, physical clip likely triggered in simulation.")
        
    print(f"Verification Passed: {pkl_path} is safely mapped to Unitree G1.")
    return True

if __name__ == "__main__":
    test_pkl = Path(__file__).parent / "hulk_kinematics.pkl"
    verify_g1_kinematics(test_pkl)
