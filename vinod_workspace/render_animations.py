"""
render_animations.py — Headless video renderer for all hero animations
-----------------------------------------------------------------------
Renders each animation to an MP4 using MuJoCo offscreen renderer.
Uses mj_kinematics (visual pose player) — no physics/gravity.

Usage:
    python render_animations.py                    # render all 10
    python render_animations.py --animation wave   # render one
    python render_animations.py --out-dir videos   # custom output dir

Output: vinod_workspace/videos/<name>.mp4
"""

import argparse
import sys
import time
import mujoco
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hero_pose import (
    STABLE_BALANCE_POSE,
    animation_wave, animation_flex, animation_punch,
    animation_hulk_smash, animation_iron_man_repulsor,
    animation_spider_man_web_shoot, animation_spider_man_landing,
    animation_captain_america_shield, animation_thor_lightning,
    animation_wolverine_claws,
)

ANIMATIONS = {
    "wave":                   animation_wave,
    "flex":                   animation_flex,
    "punch":                  animation_punch,
    "hulk_smash":             animation_hulk_smash,
    "iron_man_repulsor":      animation_iron_man_repulsor,
    "spider_man_web_shoot":   animation_spider_man_web_shoot,
    "spider_man_landing":     animation_spider_man_landing,
    "captain_america_shield": animation_captain_america_shield,
    "thor_lightning":         animation_thor_lightning,
    "wolverine_claws":        animation_wolverine_claws,
}

SCENE_XML = (
    Path(__file__).parent.parent
    / "kim_workspace" / "hardware_deployment"
    / "unitree_mujoco" / "unitree_robots" / "g1" / "scene.xml"
)

WIDTH, HEIGHT = 640, 480
FPS = 30
HOLD_SECONDS = 1.0


def build_joint_map(model):
    name_to_ctrl = {}
    for i in range(model.nu):
        if model.actuator_trntype[i] != mujoco.mjtTrn.mjTRN_JOINT:
            continue
        tid = model.actuator_trnid[i, 0]
        jname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, tid)
        name_to_ctrl[jname] = int(model.jnt_qposadr[tid])
    return name_to_ctrl


def pose_to_qpos(pose, name_to_ctrl, data):
    for jname, angle in pose.items():
        if jname in name_to_ctrl:
            data.qpos[name_to_ctrl[jname]] = angle


def render_animation(model, data, renderer, name_to_ctrl, anim_name, frames, out_path):
    try:
        import cv2
    except ImportError:
        print("[ERROR] opencv-python required: pip install opencv-python")
        sys.exit(1)

    # Build full trajectory: hold + animation + hold
    hold_frames = int(HOLD_SECONDS * FPS)
    trajectory = [STABLE_BALANCE_POSE] * hold_frames + frames + [STABLE_BALANCE_POSE] * hold_frames

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )

    # Camera: slightly elevated, facing the robot
    renderer.update_scene(data, camera=-1)

    for i, pose in enumerate(trajectory):
        # Reset to stable base, then apply pose
        data.qpos[:7] = [0.0, 0.0, 0.787, 1.0, 0.0, 0.0, 0.0]
        pose_to_qpos(STABLE_BALANCE_POSE, name_to_ctrl, data)
        pose_to_qpos(pose, name_to_ctrl, data)
        mujoco.mj_kinematics(model, data)

        renderer.update_scene(data)
        pixels = renderer.render()  # (H, W, 3) RGB

        bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
        writer.write(bgr)

    writer.release()
    duration = len(trajectory) / FPS
    print(f"  {anim_name:<30} → {out_path.name}  ({len(trajectory)} frames, {duration:.1f}s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--animation", choices=list(ANIMATIONS.keys()),
                        help="Render a single animation (default: all)")
    parser.add_argument("--out-dir", default="videos",
                        help="Output directory (default: vinod_workspace/videos/)")
    args = parser.parse_args()

    if not SCENE_XML.exists():
        print(f"[ERROR] scene.xml not found: {SCENE_XML}")
        sys.exit(1)

    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    data = mujoco.MjData(model)
    name_to_ctrl = build_joint_map(model)

    # Setup offscreen renderer
    renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)

    # Position camera
    data.qpos[:7] = [0.0, 0.0, 0.787, 1.0, 0.0, 0.0, 0.0]
    pose_to_qpos(STABLE_BALANCE_POSE, name_to_ctrl, data)
    mujoco.mj_kinematics(model, data)

    out_dir = Path(__file__).parent / args.out_dir
    to_render = {args.animation: ANIMATIONS[args.animation]} if args.animation else ANIMATIONS

    print(f"Rendering {len(to_render)} animation(s) → {out_dir}/")
    t0 = time.monotonic()
    for name, func in to_render.items():
        frames = func()
        render_animation(model, data, renderer, name_to_ctrl, name, frames, out_dir / f"{name}.mp4")

    print(f"\nDone in {time.monotonic()-t0:.1f}s")


if __name__ == "__main__":
    main()
