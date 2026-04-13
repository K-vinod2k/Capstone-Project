#!/usr/bin/env python3
"""
Generate Kim's RAG dataset: 10 hero animations → (N×35) pkl files + descriptors.json

Output: vinod_workspace/rag_dataset/<name>_kinematics.pkl  (one per animation)
        vinod_workspace/kim_rag_database.zip               (everything zipped for handoff)
        vinod_workspace/rag_dataset/descriptors.json       (text descriptions for vector store)

Usage:
    python generate_rag_dataset.py
"""
import json
import pickle
import sys
import zipfile
import numpy as np
from pathlib import Path

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

import mujoco

SCENE_XML = (
    Path(__file__).parent.parent
    / "kim_workspace" / "hardware_deployment"
    / "unitree_mujoco" / "unitree_robots" / "g1" / "scene.xml"
)

ANIMATIONS = {
    "wave":                    animation_wave,
    "flex":                    animation_flex,
    "punch":                   animation_punch,
    "hulk_smash":              animation_hulk_smash,
    "iron_man_repulsor":       animation_iron_man_repulsor,
    "spider_man_web_shoot":    animation_spider_man_web_shoot,
    "spider_man_landing":      animation_spider_man_landing,
    "captain_america_shield":  animation_captain_america_shield,
    "thor_lightning":          animation_thor_lightning,
    "wolverine_claws":         animation_wolverine_claws,
}

# Text descriptions Kim will embed into her vector store.
# Each entry: query phrases a user might type → maps to this animation.
DESCRIPTORS = {
    "wave": (
        "Wave hello or goodbye. Friendly greeting with one arm raised and moving side to side. "
        "Use for: wave, hello, hi, greet, goodbye, bye, salute casually."
    ),
    "flex": (
        "Flex both arms showing muscles. Power pose with elbows bent and fists raised. "
        "Use for: flex, show muscles, strong, power up, bicep, pose, intimidate."
    ),
    "punch": (
        "Throw a straight punch forward with the right arm. Aggressive striking motion. "
        "Use for: punch, hit, strike, attack, jab, fight, knock out."
    ),
    "hulk_smash": (
        "Overhead two-arm slam downward with full force. Both arms raised then driven down. "
        "Use for: hulk smash, slam, smash, crush, overhead strike, destroy, pound."
    ),
    "iron_man_repulsor": (
        "Extend both arms forward palms out firing repulsor beams. Defensive blast pose. "
        "Use for: repulsor, blast, fire, shoot beams, iron man, hands forward, push away."
    ),
    "spider_man_web_shoot": (
        "Point one arm forward and flick wrist to shoot a web. Quick wrist snap gesture. "
        "Use for: web shoot, thwip, spider-man, shoot web, swing, point and fire."
    ),
    "spider_man_landing": (
        "Crouch low in three-point landing pose, one hand touching ground. "
        "Use for: land, crouch, three point landing, spider-man pose, touch down, kneel."
    ),
    "captain_america_shield": (
        "Raise left arm in a defensive shield block stance, feet planted wide. "
        "Use for: shield, block, defend, protect, captain america, guard, cover."
    ),
    "thor_lightning": (
        "Raise one arm straight up holding hammer calling lightning, chin lifted. "
        "Use for: lightning, thunder, thor, hammer, call storm, raise arm, charge up."
    ),
    "wolverine_claws": (
        "Extend both arms outward with wrists cocked, claws out in fighting stance. "
        "Use for: claws, wolverine, slash, blades out, berserker, ready to fight, snarl."
    ),
}


PKL_FPS            = 30.0
MAX_JOINT_VEL      = 2.0    # rad/s — conservative hardware safe limit (hardware abort is 8 rad/s)
MAX_DELTA_PER_FRAME = MAX_JOINT_VEL / PKL_FPS   # 0.067 rad/frame


def velocity_clamp(mat: np.ndarray) -> np.ndarray:
    """
    Ensure no joint moves faster than MAX_JOINT_VEL between consecutive pkl frames.
    Inserts linear interpolation steps where needed.
    Returns a new (N', 35) array where N' >= N.
    """
    out = [mat[0]]
    for i in range(1, len(mat)):
        delta = mat[i] - out[-1]
        max_d = np.max(np.abs(delta))
        if max_d > MAX_DELTA_PER_FRAME:
            # Number of intermediate steps needed
            steps = int(np.ceil(max_d / MAX_DELTA_PER_FRAME))
            for s in range(1, steps + 1):
                out.append(out[-1] + delta * (s / steps))
        else:
            out.append(mat[i])
    result = np.stack(out, axis=0).astype(np.float32)
    return result


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


def animation_to_matrix(frames: list, name_to_ctrl: dict, nu: int) -> np.ndarray:
    """Convert list of pose dicts → (N, 35) float32 array seeded from STABLE_BALANCE_POSE."""
    N = len(frames)
    mat = np.zeros((N, 35), dtype=np.float32)

    # Build stable baseline as a (nu,) array
    baseline = np.zeros(nu, dtype=np.float32)
    for jname, angle in STABLE_BALANCE_POSE.items():
        if jname in name_to_ctrl:
            baseline[name_to_ctrl[jname]] = angle

    for i, pose_dict in enumerate(frames):
        row = baseline.copy()
        for jname, angle in pose_dict.items():
            if jname in name_to_ctrl:
                row[name_to_ctrl[jname]] = angle
        mat[i, :nu] = row  # indices nu..34 stay 0 (extended joints)

    return mat


def main():
    if not SCENE_XML.exists():
        print(f"[ERROR] scene.xml not found: {SCENE_XML}")
        sys.exit(1)

    print("Loading MuJoCo model...")
    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    name_to_ctrl, _ = build_joint_maps(model)
    print(f"  nu={model.nu}, joints mapped: {len(name_to_ctrl)}")

    out_dir = Path(__file__).parent / "rag_dataset"
    out_dir.mkdir(exist_ok=True)

    generated = []
    for name, func in ANIMATIONS.items():
        frames = func()
        mat = animation_to_matrix(frames, name_to_ctrl, model.nu)
        mat = velocity_clamp(mat)
        pkl_path = out_dir / f"{name}_kinematics.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump({"joint_angles": mat}, f)
        generated.append(pkl_path)
        peak_vel = float(np.max(np.abs(np.diff(mat, axis=0))) * PKL_FPS)
        print(f"  {name}_kinematics.pkl  ({len(frames)}→{len(mat)} frames, peak={peak_vel:.2f} rad/s)")

    # Write descriptors for Kim's vector store
    desc_path = out_dir / "descriptors.json"
    with open(desc_path, "w") as f:
        json.dump(DESCRIPTORS, f, indent=2)
    generated.append(desc_path)
    print(f"  descriptors.json  ({len(DESCRIPTORS)} entries)")

    # Zip everything for handoff
    zip_path = Path(__file__).parent / "kim_rag_database.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in generated:
            zf.write(p, p.name)

    print(f"\nDone. Archive: {zip_path}  ({zip_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
