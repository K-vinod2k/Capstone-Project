#!/usr/bin/env python3
import os
import sys
import pickle
import zipfile
import numpy as np
import mujoco
from pathlib import Path

# Provide standard physics dependencies
sys.path.insert(0, str(Path(__file__).parent))
from hero_pose import (
    STABLE_BALANCE_POSE,
    animation_wave,
    animation_flex,
    animation_punch,
    animation_hulk_smash,
    animation_iron_man_repulsor,
    animation_spider_man_web_shoot,
    animation_spider_man_landing,
    animation_captain_america_shield,
    animation_thor_lightning,
    animation_wolverine_claws,
)

ANIMATIONS = {
    "wave": animation_wave,
    "flex": animation_flex,
    "punch": animation_punch,
    "hulk_smash": animation_hulk_smash,
    "iron_man_repulsor": animation_iron_man_repulsor,
    "spider_man_web_shoot": animation_spider_man_web_shoot,
    "spider_man_landing": animation_spider_man_landing,
    "captain_america_shield": animation_captain_america_shield,
    "thor_lightning": animation_thor_lightning,
    "wolverine_claws": animation_wolverine_claws,
}

SCENE_XML = (
    Path(__file__).parent.parent
    / "kim_workspace" / "hardware_deployment"
    / "unitree_mujoco" / "unitree_robots" / "g1" / "scene.xml"
)

def build_joint_maps(model: mujoco.MjModel):
    name_to_ctrl = {}
    qpos_list = [0] * model.nu
    for i in range(model.nu):
        if model.actuator_trntype[i] != mujoco.mjtTrn.mjTRN_JOINT:
            continue
        trnid = model.actuator_trnid[i, 0]
        jname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, trnid)
        name_to_ctrl[jname] = i
        qpos_list[i] = int(model.jnt_qposadr[trnid])
    return name_to_ctrl, qpos_list

def main():
    if not SCENE_XML.exists():
        print(f"Error: {SCENE_XML} not found.")
        sys.exit(1)
        
    print("Loading MuJoCo model to extract exact hardware topology...")
    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    data = mujoco.MjData(model)
    name_to_ctrl, qpos_idx = build_joint_maps(model)
    
    out_dir = Path(__file__).parent / "rag_dataset"
    out_dir.mkdir(exist_ok=True)
    
    # Process all 10 animations
    generated_files = []
    print(f"Generating 35-DOF '.pkl' arrays for Kim's database...")
    
    for name, func in ANIMATIONS.items():
        frames = func()
        # Each animation is a list of hero_pose dictionaries.
        # We need an N x 35 numpy array.
        N = len(frames)
        # Pre-seed with stable balance pose to avoid snapping
        mat = np.zeros((N, 35), dtype=np.float32)
        
        for frame_idx, pose_dict in enumerate(frames):
            # Fill with stable default, then override with pose
            target = np.zeros(29)
            for jname, angle in STABLE_BALANCE_POSE.items():
                if jname in name_to_ctrl:
                    target[name_to_ctrl[jname]] = angle
            for jname, angle in pose_dict.items():
                if jname in name_to_ctrl:
                    target[name_to_ctrl[jname]] = angle
                    
            # Set the first 29 hardware indices
            size = min(len(target), 35)
            mat[frame_idx, :size] = target[:size]
            
        pkl_path = out_dir / f"{name}_kinematics.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump({"joint_angles": mat}, f)
        
        generated_files.append(pkl_path)
        print(f"  -> Generated {name_kinematics.pkl if 'name_kinematics' in locals() else f'{name}_kinematics.pkl'} ({N} frames)")
        
    print("Compressing RAG dataset for handoff...")
    zip_path = Path(__file__).parent / "kim_rag_database.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in generated_files:
            zipf.write(file, file.name)
            
    print(f"Done! Final archive created: {zip_path}")

if __name__ == "__main__":
    main()
