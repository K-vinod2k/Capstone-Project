import mujoco
import mujoco.viewer
import time
import pickle
import numpy as np
from pathlib import Path

def preview_hulk():
    # 1. Locate the physical G1 model XML
    g1_xml = Path(__file__).parent / "video2robot" / "third_party" / "GMR" / "assets" / "unitree_g1" / "g1_mocap_29dof.xml"
    if not g1_xml.exists():
        g1_xml = Path(__file__).parent / "video2robot" / "third_party" / "GMR" / "assets" / "unitree_g1" / "g1_mocap_29dof_with_hands.xml"
        
    if not g1_xml.exists():
        print(f"Error: Could not find G1 XML at {g1_xml}")
        return

    try:
        model = mujoco.MjModel.from_xml_path(str(g1_xml))
        data = mujoco.MjData(model)
    except Exception as e:
        print(f"Failed to load MuJoCo model: {e}")
        return

    # 2. Load the kinematics PKL
    pkl_path = Path(__file__).parent / "hulk_kinematics.pkl"
    if not pkl_path.exists():
        print(f"Error: Kinematics not found at {pkl_path}")
        print("Have you run headless_extraction.py yet?")
        return
        
    with open(pkl_path, "rb") as f:
        kinematics = pickle.load(f)
        
    joints = kinematics.get("joint_angles", [])
    if len(joints) == 0:
        print("No 'joint_angles' structure found in .pkl")
        return

    print("Launching MuJoCo Viewer... Close the window to stop.")
    try:
        # 3. Launch UI Window and Iterate
        with mujoco.viewer.launch_passive(model, data) as viewer:
            # Drop the robot base a bit so it doesn't fall endlessly
            data.qpos[2] = 0.8
            
            for frame in joints:
                if not viewer.is_running():
                    break
                    
                # Assuming 29 to 35 DOF matches the Unitree motor schema order
                # qpos[0:7] is the root free joint (x, y, z, q1, q2, q3, q4)
                dof_len = len(data.qpos) - 7
                data.qpos[7:] = frame[:dof_len] 
                
                # We forward kinematics (mj_kinematics) instead of mj_step so it acts as 
                # a pure visual pose-player rather than a physical falling ragdoll.
                mujoco.mj_kinematics(model, data)
                viewer.sync()
                
                time.sleep(1/30.0) # 30 FPS playback
        print("Playback finished.")
    except Exception as e:
        print(f"Visualizer Error (Do you have mujoco installed locally?): {e}")

if __name__ == "__main__":
    preview_hulk()
