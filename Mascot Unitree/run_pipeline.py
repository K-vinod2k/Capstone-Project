"""
run_pipeline.py — Standalone CLI for the Mascot Unitree pipeline.

Usage:
  python run_pipeline.py                        # interactive text loop
  python run_pipeline.py --voice                # microphone input loop
  python run_pipeline.py --text "Hey Spider-Man, do something cool!"
  python run_pipeline.py --text "..." --no-video  # skip video gen (fast test)
  python run_pipeline.py --text "..." --speak     # speak reply via macOS 'say'
  python run_pipeline.py --loop                   # keep looping for multiple commands
"""

import argparse
import asyncio
import base64
import os
import pickle
import shlex
import threading
import time
import warnings
from pathlib import Path

import scipy.io.wavfile as wav
import sounddevice as sd
import whisper
from dotenv import load_dotenv

from persona_brain import generate_robot_response
from pipeline import (
    PHYSICAL_BOOSTER, generate_video, render_mujoco_trajectory,
    render_unitree_frame, verify_stability, video_ready,
)


warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")


def speak(text: str):
    os.system(f"say {shlex.quote(text)}")


class Ear:
    def __init__(self, model_name="base"):
        self._model = None
        self._name = model_name
        self._fs = 16000

    def listen(self, duration=5, filename="temp_command.wav") -> str:
        if self._model is None:
            print(f"🧠 [Ear] Loading Whisper '{self._name}'...")
            self._model = whisper.load_model(self._name)
        print(f"🎙️  Listening for {duration}s...")
        audio = sd.rec(int(duration * self._fs), samplerate=self._fs, channels=1, dtype="int16")
        sd.wait()
        wav.write(filename, self._fs, audio)
        text = self._model.transcribe(filename)["text"].strip()
        print(f"📝 {text}")
        return text

load_dotenv()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


async def run_pipeline(user_prompt: str, skip_video: bool = False, speak: bool = False):
    ts = int(time.time())
    print(f"\n{'='*60}\nINPUT: {user_prompt}\n{'='*60}")

    # 1. Persona engine
    response         = generate_robot_response(user_prompt)
    spoken_reply     = response.get("spoken_reply", "Ready.")
    gesture_desc     = response.get("gesture_description", "Standing still.")
    detected_hero    = response.get("detected_persona", "Generic Hero")
    hero_icon        = response.get("hero_icon", "🤖")

    print(f"\n🎭 Hero: {detected_hero} {hero_icon}")
    print(f"💬 Says: {spoken_reply}")
    print(f"🎬 Gesture: {gesture_desc}")

    if speak:
        threading.Thread(target=speak, args=(spoken_reply,), daemon=True).start()

    # 2. Physics gate (Cosmos-Reason2 + Unitree G1 render)
    robot_frame = render_unitree_frame()
    physics = verify_stability(gesture_desc, robot_frame_b64=robot_frame)
    if physics.get("chain_of_thought"):
        print(f"🧠 Reason2: {physics['chain_of_thought'][:200]}")
    if not physics["is_stable"]:
        print(f"\n⛔ Physics gate blocked: {physics['reasoning']}")
        return
    print(f"✅ Physics: {physics['reasoning']}")

    # 3. Video generation
    ref_video_b64 = None

    if skip_video:
        print("\n⏭  Skipping video generation (--no-video)")
    elif not video_ready:
        print("\n⚠️  No video backend — set FAL_KEY or COLAB_URL in .env")
    else:
        print("\n🎬 Generating video...")
        result = generate_video(gesture_desc + PHYSICAL_BOOSTER, duration=6, resolution="720p")
        if result.get("success"):
            ref_video_b64 = result["video_base64"]
            ref_path = OUTPUT_DIR / f"ref_{ts}.mp4"
            ref_path.write_bytes(base64.b64decode(ref_video_b64))
            print(f"✅ Reference video → {ref_path}")

        else:
            print(f"⚠️  Video generation failed: {result.get('error')}")

    # 4. Motion — load pre-computed G1 demo motion
    DEMO_PKL = Path(__file__).parent / "output" / "2026-03-12_07-07-09.pkl"
    with open(DEMO_PKL, "rb") as f:
        trajectory = pickle.load(f)
    print(f"✅ Loaded demo motion: {len(trajectory['dof_pos'])} frames")

    # 5. Render simulation
    sim_path = str(OUTPUT_DIR / f"sim_{ts}.mp4")
    print("\n🤖 Rendering simulation...")
    render_mujoco_trajectory(trajectory, sim_path)

    ref_path = OUTPUT_DIR / f"ref_{ts}.mp4" if ref_video_b64 else None
    print(f"\n{'='*60}")
    if ref_path and ref_path.exists():
        print(f"  Reference : {ref_path}")
    print(f"  Simulation: {sim_path}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Mascot Unitree pipeline")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--text", "-t", help="Text prompt")
    group.add_argument("--voice", "-v", action="store_true", help="Microphone input (Whisper)")
    parser.add_argument("--no-video", action="store_true", help="Skip video generation")
    parser.add_argument("--speak", action="store_true", help="Speak reply via macOS 'say'")
    parser.add_argument("--loop", action="store_true", help="Keep looping for multiple commands")
    args = parser.parse_args()

    if args.voice or args.loop:
        ear = Ear(model_name="base")

    async def _run(prompt):
        await run_pipeline(prompt, skip_video=args.no_video, speak=args.speak)

    if args.text and not args.loop:
        asyncio.run(_run(args.text))
        return

    print("Mascot Unitree  |  type 'quit' to exit\n")
    while True:
        if args.voice:
            prompt = ear.listen(duration=5)
        else:
            try:
                prompt = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

        if not prompt or prompt.lower() in ("quit", "exit", "q"):
            break

        asyncio.run(_run(prompt))

        if not args.loop:
            break


if __name__ == "__main__":
    main()
