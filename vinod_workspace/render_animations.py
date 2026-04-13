"""
render_animations.py — Headless video renderer for all hero animations
-----------------------------------------------------------------------
Renders from velocity-clamped PKL files (kim_workspace/movements/) so
videos exactly match what the robot will do — same frame count, same speed.

Usage:
    python render_animations.py                    # render all 10
    python render_animations.py --animation wave   # render one

Output: vinod_workspace/videos/<name>.mp4
"""

import argparse
import pickle
import sys
import time
import numpy as np
import mujoco
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SCENE_XML = (
    Path(__file__).parent.parent
    / "kim_workspace" / "hardware_deployment"
    / "unitree_mujoco" / "unitree_robots" / "g1" / "scene.xml"
)

MOVEMENTS_DIR = Path(__file__).parent.parent / "kim_workspace" / "movements"

ANIMATION_NAMES = [
    "wave", "flex", "punch", "hulk_smash", "iron_man_repulsor",
    "spider_man_web_shoot", "spider_man_landing",
    "captain_america_shield", "thor_lightning", "wolverine_claws",
]

WIDTH, HEIGHT = 640, 480
FPS = 30
HOLD_SECONDS = 1.0

# 23-DOF hardware IDL index → MuJoCo 29-DOF actuator index (for visualization)
IDL_23DOF_TO_MUJOCO_ACT = {
    **{i: i for i in range(13)},  # legs + waist_yaw: identical
    13: 15,   # L_shoulder_pitch
    14: 16,   # L_shoulder_roll
    15: 17,   # L_shoulder_yaw
    16: 18,   # L_elbow
    # 17 (L_elbow_roll): no MuJoCo equivalent — skip
    18: 22,   # R_shoulder_pitch
    19: 23,   # R_shoulder_roll
    20: 24,   # R_shoulder_yaw
    21: 25,   # R_elbow
    # 22 (R_elbow_roll): no MuJoCo equivalent — skip
}


def build_act_to_qpos(model):
    """Map MuJoCo actuator index → qpos address."""
    act_to_qpos = {}
    for i in range(model.nu):
        if model.actuator_trntype[i] != mujoco.mjtTrn.mjTRN_JOINT:
            continue
        tid = model.actuator_trnid[i, 0]
        act_to_qpos[i] = int(model.jnt_qposadr[tid])
    return act_to_qpos


def apply_pkl_frame(frame_35, act_to_qpos, data):
    """Apply one PKL frame (23-DOF IDL layout) to MuJoCo qpos."""
    for idl_idx, mj_act in IDL_23DOF_TO_MUJOCO_ACT.items():
        if mj_act in act_to_qpos:
            data.qpos[act_to_qpos[mj_act]] = float(frame_35[idl_idx])


def apply_stable_pose(act_to_qpos, data):
    """Reset to standing balance pose via MuJoCo actuator indices."""
    # Use the first frame's leg values (already from STABLE_BALANCE_POSE)
    # Hard-code the known standing angles directly
    standing = {0: -0.3, 3: 0.6, 4: -0.3,   # left leg
                6: -0.3, 9: 0.6, 10: -0.3}   # right leg
    for act, angle in standing.items():
        if act in act_to_qpos:
            data.qpos[act_to_qpos[act]] = angle


def render_from_pkl(model, data, renderer, act_to_qpos, name, out_path):
    try:
        import cv2
    except ImportError:
        print("[ERROR] pip install opencv-python")
        sys.exit(1)

    pkl_path = MOVEMENTS_DIR / f"{name}_kinematics.pkl"
    if not pkl_path.exists():
        print(f"  [SKIP] {pkl_path.name} not found")
        return

    with open(pkl_path, "rb") as f:
        joints = np.array(pickle.load(f)["joint_angles"], dtype=np.float32)

    hold = int(HOLD_SECONDS * FPS)
    total = hold + len(joints) + hold

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"),
                             FPS, (WIDTH, HEIGHT))

    for i in range(total):
        data.qpos[:7] = [0.0, 0.0, 0.787, 1.0, 0.0, 0.0, 0.0]
        apply_stable_pose(act_to_qpos, data)

        if hold <= i < hold + len(joints):
            apply_pkl_frame(joints[i - hold], act_to_qpos, data)

        mujoco.mj_kinematics(model, data)
        renderer.update_scene(data)
        bgr = __import__("cv2").cvtColor(renderer.render(), __import__("cv2").COLOR_RGB2BGR)
        writer.write(bgr)

    writer.release()
    print(f"  {name:<30} → {out_path.name}  ({len(joints)} frames, {len(joints)/FPS:.1f}s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--animation", choices=ANIMATION_NAMES,
                        help="Render one animation (default: all)")
    args = parser.parse_args()

    if not SCENE_XML.exists():
        print(f"[ERROR] scene.xml not found: {SCENE_XML}")
        sys.exit(1)

    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    data = mujoco.MjData(model)
    act_to_qpos = build_act_to_qpos(model)
    renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)

    out_dir = Path(__file__).parent / "videos"
    names = [args.animation] if args.animation else ANIMATION_NAMES

    print(f"Rendering {len(names)} animation(s) from PKL files → {out_dir}/")
    t0 = time.monotonic()
    for name in names:
        render_from_pkl(model, data, renderer, act_to_qpos, name, out_dir / f"{name}.mp4")

    print(f"\nDone in {time.monotonic()-t0:.1f}s")


if __name__ == "__main__":
    main()
