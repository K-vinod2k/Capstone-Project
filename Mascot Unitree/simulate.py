"""
simulate.py — Render a robot simulation from an existing video or pkl file.

Usage:
  python simulate.py --pkl output/2026-03-12_07-07-09.pkl
  python simulate.py --pkl output/2026-03-12_07-07-09.pkl --physics
  python simulate.py --video output/colab_output.mp4
  python simulate.py --video output/colab_output.mp4 --out output/my_sim.mp4
"""

import argparse
import base64
import pickle
import sys
from pathlib import Path

from pipeline import render_mujoco_trajectory, run_video2robot_pipeline


def from_pkl(pkl_path: str, out_path: str, physics: bool = False):
    print(f"Loading motion from {pkl_path} ...")
    with open(pkl_path, "rb") as f:
        trajectory = pickle.load(f)
    frames = len(trajectory.get("dof_pos", []))
    print(f"  {frames} frames  |  keys: {list(trajectory.keys())}")
    mode = "physics+gravity" if physics else "kinematics"
    print(f"Rendering [{mode}] → {out_path}")
    render_mujoco_trajectory(trajectory, out_path, physics=physics)
    print(f"✅ Done: {out_path}")


def from_video(video_path: str, out_path: str, physics: bool = False):
    print(f"Running Video2Robot on {video_path} ...")
    video_b64 = base64.b64encode(Path(video_path).read_bytes()).decode()
    trajectory = run_video2robot_pipeline(video_b64)
    if not trajectory:
        print("⛔ Video2Robot failed — check phmr + gmr conda envs in ../video2robot/")
        sys.exit(1)
    print(f"✅ {len(trajectory.get('dof_pos', []))} frames extracted")
    mode = "physics+gravity" if physics else "kinematics"
    print(f"Rendering [{mode}] → {out_path}")
    render_mujoco_trajectory(trajectory, out_path, physics=physics)

    # save pkl alongside for reuse
    pkl_path = Path(out_path).with_suffix(".pkl")
    with open(pkl_path, "wb") as f:
        pickle.dump(trajectory, f)
    print(f"✅ Done: {out_path}")
    print(f"   Motion saved: {pkl_path}")


def main():
    parser = argparse.ArgumentParser(description="Simulate robot from video or pkl")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", "-v", help="Reference video (MP4) to run through Video2Robot")
    src.add_argument("--pkl",   "-p", help="Pre-computed robot_motion.pkl to render directly")
    parser.add_argument("--out", "-o", default=None,
                        help="Output MP4 path (default: output/sim_<source>.mp4)")
    parser.add_argument("--physics", action="store_true",
                        help="Enable gravity + PD physics instead of pure kinematics")
    args = parser.parse_args()

    Path("output").mkdir(exist_ok=True)

    if args.video:
        stem = Path(args.video).stem
        out = args.out or f"output/sim_{stem}.mp4"
        from_video(args.video, out, physics=args.physics)
    else:
        stem = Path(args.pkl).stem
        out = args.out or f"output/sim_{stem}.mp4"
        from_pkl(args.pkl, out, physics=args.physics)


if __name__ == "__main__":
    main()
