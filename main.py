from kim_workspace.robot_persona.src import RobotPersona
from kim_workspace.stt.src import STT
import sounddevice as sd
from dotenv import load_dotenv
import os
import pickle
import numpy as np

def pickle_to_movement(path):
    """
    Load a hero animation pkl file and replay it.

    On Mac/sim: plays through MuJoCo physics evaluator (non-blocking thread).
    On hardware: delegates to g1_arm_replay_airborne via DDS (interface=eth0).

    Input:
        path: str — path to a *_kinematics.pkl with {'joint_angles': ndarray(N, 35)}
    """
    if not path or not os.path.exists(path):
        print(f"[MOVEMENT] pkl not found: {path}")
        return

    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
    except Exception as e:
        print(f"[MOVEMENT] Failed to load pkl: {e}")
        return

    if not isinstance(data, dict):
        print(f"[MOVEMENT] Invalid pkl format (expected dict, got {type(data).__name__})")
        return

    joints = data.get("joint_angles")
    if joints is None or len(joints) == 0:
        print(f"[MOVEMENT] Empty or invalid pkl: {path}")
        return

    joints = np.array(joints, dtype=np.float32)
    n_frames = len(joints)
    anim_name = os.path.splitext(os.path.basename(path))[0].replace("_kinematics", "")

    print(f"[MOVEMENT] Playing '{anim_name}' — {n_frames} frames")

    # Detect hardware vs simulation
    interface = os.getenv("ROBOT_INTERFACE", "lo")  # set ROBOT_INTERFACE=eth0 for real robot

    if interface == "eth0":
        _replay_hardware(joints, interface)
    else:
        _replay_sim(anim_name)


def _replay_sim(anim_name: str):
    """Render animation to MP4 and open it."""
    import sys, subprocess
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "vinod_workspace"))

    render_script = Path(__file__).parent / "vinod_workspace" / "render_animations.py"
    video_path = Path(__file__).parent / "vinod_workspace" / "videos" / f"{anim_name}.mp4"

    # Use pre-rendered video if it exists, otherwise render it now
    if not video_path.exists():
        print(f"[MOVEMENT] Rendering {anim_name}...")
        subprocess.run([sys.executable, str(render_script), "--animation", anim_name],
                       capture_output=True)

    if video_path.exists():
        print(f"[MOVEMENT] Opening {video_path.name}")
        subprocess.Popen(["open", str(video_path)])  # macOS: opens in QuickTime
    else:
        print(f"[MOVEMENT] Video not found for '{anim_name}'")


def _replay_hardware(joints: np.ndarray, interface: str):
    """Send joint angles to real G1 via DDS at 200 Hz."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "kim_workspace" / "hardware_deployment"))

    try:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber, ChannelPublisher
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_, LowCmd_
        from g1_arm_replay_airborne import ArmReplayController, LEFT_ARM, load_pkl
        import tempfile, pickle as pk

        # Write joints to a temp pkl so load_pkl can validate it
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
            pk.dump({"joint_angles": joints}, tmp)
            tmp_path = tmp.name

        frames = load_pkl(tmp_path)
        ChannelFactoryInitialize(1, interface)
        controller = ArmReplayController(frames, LEFT_ARM)

        sub = ChannelSubscriber("rt/lowstate", LowState_)
        sub.Init(controller.on_low_state, 10)
        pub = ChannelPublisher("rt/lowcmd", LowCmd_)
        pub.Init()

        controller.run(pub)
    except ImportError:
        print("[MOVEMENT] unitree_sdk2py not available — hardware replay skipped")
    except Exception as e:
        print(f"[MOVEMENT] Hardware replay error: {e}")


if __name__ == "__main__":

    # Input Variables
    persona_name = "a Superhero"
    movement_directory = './kim_workspace/movements'

    # Models
    load_dotenv()
    persona = RobotPersona(persona_name, movement_directory)

    import sys
    text_mode = "--text" in sys.argv or not sys.stdin.isatty() is False

    if "--text" in sys.argv:
        # Text input mode — no microphone needed
        print("Text mode. Type a command (Ctrl+C to quit).\n")
        while True:
            try:
                user_input = input("[YOU] ").strip()
                if not user_input:
                    continue
                result = persona.forward(user_input)
                pickle_to_movement(result['gesture'])
            except KeyboardInterrupt:
                print("\nBye.")
                break
    else:
        # Voice mode
        import sounddevice as sd
        from kim_workspace.stt.src import STT
        stt = STT()
        stream = sd.InputStream(samplerate=stt.SAMPLERATE,
                            channels=1,
                            callback=stt.audio_callback)
        with stream:
            stt.process_audio(persona.forward, pickle_to_movement)
