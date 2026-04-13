"""
example.py — Mascot Unitree End-to-End Demo
============================================

What this does:
  1. You type any text (e.g. "do something cool", "iron man", "hulk")
  2. RAG retrieves the closest hero animation
  3. Robot replies with a hero quote
  4. Animation plays:
       - Mac/sim  → opens pre-rendered MP4 in QuickTime
       - Real G1  → set ROBOT_INTERFACE=eth0, deploys via DDS

Run:
    python example.py

Real robot:
    ROBOT_INTERFACE=eth0 python example.py
"""

import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent
MOVEMENTS    = ROOT / "kim_workspace" / "movements"
VIDEOS       = ROOT / "vinod_workspace" / "videos"
RENDER_SCRIPT = ROOT / "vinod_workspace" / "render_animations.py"

# ── Hero replies ────────────────────────────────────────────────────────────
REPLIES = {
    "wave":                   "Hey there! *waves*",
    "flex":                   "Nobody is stronger than me!",
    "punch":                  "Take that!",
    "hulk_smash":             "HULK SMASH!",
    "iron_man_repulsor":      "Repulsors online. Back off.",
    "spider_man_web_shoot":   "Your friendly neighborhood Spider-Man!",
    "spider_man_landing":     "Just dropped in.",
    "captain_america_shield": "I can do this all day.",
    "thor_lightning":         "I am the God of Thunder!",
    "wolverine_claws":        "I'm the best there is at what I do.",
}

# ── RAG retrieval ───────────────────────────────────────────────────────────
def load_retriever():
    sys.path.insert(0, str(ROOT / "vinod_workspace"))
    from rag_retrieve import MotionRetriever
    return MotionRetriever()

# ── Playback ────────────────────────────────────────────────────────────────
def play(pkl_path: str):
    if not pkl_path or not os.path.exists(pkl_path):
        print(f"[MOVEMENT] file not found: {pkl_path}")
        return

    try:
        data = pickle.load(open(pkl_path, "rb"))
    except Exception as e:
        print(f"[MOVEMENT] load error: {e}")
        return

    joints = np.array(data.get("joint_angles", []), dtype=np.float32)
    if len(joints) == 0:
        print("[MOVEMENT] empty pkl")
        return

    anim = Path(pkl_path).stem.replace("_kinematics", "")
    print(f"[MOVEMENT] {anim}  ({len(joints)} frames, {len(joints)/30:.1f}s)")

    if os.getenv("ROBOT_INTERFACE") == "eth0":
        _deploy_hardware(joints)
    else:
        _play_video(anim)


def _play_video(anim: str):
    video = VIDEOS / f"{anim}.mp4"
    if not video.exists():
        print(f"[VIDEO] rendering {anim}...")
        subprocess.run([sys.executable, str(RENDER_SCRIPT), "--animation", anim],
                       capture_output=True)
    if video.exists():
        subprocess.Popen(["open", str(video)])
    else:
        print(f"[VIDEO] not found: {video.name}")


def _deploy_hardware(joints: np.ndarray):
    try:
        import tempfile
        from unitree_sdk2py.core.channel import (
            ChannelFactoryInitialize, ChannelSubscriber, ChannelPublisher)
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_, LowCmd_
        sys.path.insert(0, str(ROOT / "kim_workspace" / "hardware_deployment"))
        from g1_arm_replay_airborne import ArmReplayController, LEFT_ARM

        tmp = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
        pickle.dump({"joint_angles": joints}, tmp)
        tmp.close()

        ChannelFactoryInitialize(1, "eth0")
        ctrl = ArmReplayController(joints, LEFT_ARM)

        sub = ChannelSubscriber("rt/lowstate", LowState_)
        sub.Init(ctrl.on_low_state, 10)
        pub = ChannelPublisher("rt/lowcmd", LowCmd_)
        pub.Init()

        ctrl.run(pub)
    except ImportError:
        print("[HARDWARE] unitree_sdk2py not available (run on Linux)")
    except Exception as e:
        print(f"[HARDWARE] error: {e}")


# ── Main loop ───────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  Mascot Unitree — Hero Pose Demo")
    print("=" * 50)
    print("Type anything. Examples:")
    print("  wave, flex, punch, iron man, spider-man,")
    print("  hulk, captain america, thor, wolverine")
    print("Ctrl+C to quit.\n")

    retriever = load_retriever()

    while True:
        try:
            text = input("[YOU] ").strip()
            if not text:
                continue

            results = retriever.query(text, top_k=1)
            pkl_path, score, anim = results[0]
            # Use movements/ (hardware-safe clamped) not rag_dataset/
            pkl_path = MOVEMENTS / f"{anim}_kinematics.pkl"
            reply = REPLIES.get(anim, "Hero mode activated!")

            print(f"[ROBOT] {reply}  (matched: {anim}, score={score:.2f})")
            play(str(pkl_path))
            print()

        except KeyboardInterrupt:
            print("\nBye.")
            break


if __name__ == "__main__":
    main()
