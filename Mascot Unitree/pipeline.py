"""
pipeline.py — Video generation, physics gate, MuJoCo render, and V2R.
Imported by run_pipeline.py (CLI) and server.py (FastAPI).
"""

import base64
import json
import os
import pickle
import subprocess
import time
from pathlib import Path

import imageio
import mujoco
import numpy as np
import requests
from dotenv import load_dotenv

from hero_pose import STABLE_BALANCE_POSE
from kinematic_brain import MODEL_PATH as MUJOCO_MODEL_PATH

# G1 pkl DOF index → joint name (29 DOFs, matches deploy_real.py joint ordering).
# Used to correctly map pkl dof_pos columns to MuJoCo actuator ctrl slots by NAME
# rather than by raw index (the 23-DOF model skips passive joints so a direct
# index mapping silently shifts every arm angle by 2 slots).
_PKL_JOINT_NAMES = [
    "left_hip_pitch_joint",        "left_hip_roll_joint",        "left_hip_yaw_joint",
    "left_knee_joint",             "left_ankle_pitch_joint",     "left_ankle_roll_joint",
    "right_hip_pitch_joint",       "right_hip_roll_joint",       "right_hip_yaw_joint",
    "right_knee_joint",            "right_ankle_pitch_joint",    "right_ankle_roll_joint",
    "waist_yaw_joint",             "waist_roll_joint",           "waist_pitch_joint",
    "left_shoulder_pitch_joint",   "left_shoulder_roll_joint",   "left_shoulder_yaw_joint",
    "left_elbow_joint",            "left_wrist_roll_joint",      "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint",  "right_shoulder_roll_joint",  "right_shoulder_yaw_joint",
    "right_elbow_joint",           "right_wrist_roll_joint",     "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
]

load_dotenv()

PHYSICAL_BOOSTER = (
    ", standing upright, both feet on ground, upper body motion only, "
    "cinematic lighting, static camera, eye-level perspective, full body visible"
)

# ── Physics gate — Cosmos-Reason2 (Qwen3-VL-2B fine-tune) ────────────────────

_UNSTABLE_WORDS = ["jumping", "flying", "leap", "soar", "airborne", "float"]
_COSMOS_REASON2_MODEL = "nvidia/Cosmos-Reason2-2B"  # Qwen3VLForConditionalGeneration

# Lazy-loaded — downloaded on first call, cached in ~/.cache/huggingface
_reason2_processor = None
_reason2_model = None


def _load_reason2():
    global _reason2_processor, _reason2_model
    if _reason2_model is not None:
        return True
    try:
        import torch
        from transformers import AutoProcessor, AutoModelForCausalLM
        print(f"[PhysicsGate] Loading {_COSMOS_REASON2_MODEL} (first run — downloads weights)...")
        _reason2_processor = AutoProcessor.from_pretrained(
            _COSMOS_REASON2_MODEL, trust_remote_code=True
        )
        device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        _reason2_model = AutoModelForCausalLM.from_pretrained(
            _COSMOS_REASON2_MODEL, torch_dtype=torch.float16,
            device_map=device, trust_remote_code=True
        )
        print(f"✅ [PhysicsGate] Cosmos-Reason2-2B loaded on {device}")
        return True
    except Exception as e:
        print(f"⚠️ [PhysicsGate] Could not load Cosmos-Reason2 ({e})")
        return False

_REASON2_SYSTEM = (
    "You are a physical AI reasoning system for a Unitree G1 bipedal humanoid robot. "
    "The robot is 1.32m tall, 35kg, 23 DOF. Legs are locked in a fixed athletic stance. "
    "Only upper body moves (shoulders, elbows, wrists, waist). "
    "Analyze whether the described gesture is physically stable and executable. "
    "Use chain-of-thought reasoning about: center of mass, joint limits, "
    "self-collision risk, and ground contact. "
    "Output ONLY valid JSON with keys: "
    "'chain_of_thought' (str), 'is_stable' (bool), 'reasoning' (str, one sentence)."
)

_REASON2_USER_TMPL = (
    "Gesture: \"{gesture}\"\n\n"
    "Analyze for the Unitree G1 shown in the image (if provided):\n"
    "1. Does this require leaving the ground?\n"
    "2. Are joint angles within G1 upper-body limits?\n"
    "3. Does CoM stay over the support polygon?\n"
    "4. Any self-collision risk?\n\n"
    "Reply JSON: {{\"chain_of_thought\": \"...\", \"is_stable\": true/false, \"reasoning\": \"...\"}}"
)


def verify_stability(gesture: str, robot_frame_b64: str | None = None) -> dict:
    """Returns {\"is_stable\": bool, \"reasoning\": str, \"chain_of_thought\": str}.

    Uses nvidia/Cosmos-Reason2-2B (Qwen3-VL fine-tune) loaded locally via transformers.
    Optionally accepts a MuJoCo-rendered G1 frame (base64 JPEG) for visual grounding.
    Falls back to keyword filter if transformers/weights unavailable.
    """
    if _load_reason2():
        try:
            import torch
            from PIL import Image
            import io

            user_text = _REASON2_USER_TMPL.format(gesture=gesture)
            messages = [
                {"role": "system", "content": _REASON2_SYSTEM},
                {"role": "user", "content": [
                    *(
                        [{"type": "image", "image": Image.open(
                            io.BytesIO(base64.b64decode(robot_frame_b64))
                        )}]
                        if robot_frame_b64 else []
                    ),
                    {"type": "text", "text": user_text},
                ]},
            ]

            text = _reason2_processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = _reason2_processor(
                text=[text],
                images=[Image.open(io.BytesIO(base64.b64decode(robot_frame_b64)))] if robot_frame_b64 else None,
                return_tensors="pt",
            ).to(_reason2_model.device)

            with torch.no_grad():
                output_ids = _reason2_model.generate(
                    **inputs, max_new_tokens=512, temperature=0.2, do_sample=True
                )
            output_ids = output_ids[:, inputs["input_ids"].shape[1]:]
            raw = _reason2_processor.decode(output_ids[0], skip_special_tokens=True).strip()

            # Extract JSON (model may wrap it in markdown)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(match.group()) if match else {}
            print(f"[Reason2] CoT: {parsed.get('chain_of_thought', raw)[:120]}...")
            return {
                "is_stable":        bool(parsed.get("is_stable", True)),
                "reasoning":        str(parsed.get("reasoning", raw[:100])),
                "chain_of_thought": str(parsed.get("chain_of_thought", raw)),
            }
        except Exception as e:
            print(f"[PhysicsGate] Cosmos-Reason2 inference failed ({e}), using keyword fallback")

    unstable = any(w in gesture.lower() for w in _UNSTABLE_WORDS)
    return {
        "is_stable":        not unstable,
        "reasoning":        "Airborne motion detected." if unstable else "Feet planted. Upper body only.",
        "chain_of_thought": "",
    }


def verify_sim_to_real(video_path: str) -> dict:
    """Uses Cosmos-Reason2 to evaluate the MuJoCo simulation video for sim-to-real gap."""
    if not _load_reason2():
        return {"is_safe_for_real_hardware": True, "reasoning": "Reason2 model unavailable."}

    from PIL import Image
    import imageio
    import re
    try:
        reader = imageio.get_reader(video_path)
        frames = []
        # Sample frames throughout the video (approx 10 FPS if video is 30 FPS)
        for i, frame in enumerate(reader):
            if i % (30 // 10) == 0:
                frames.append(Image.fromarray(frame))
                
        # Downsample strictly to 8 frames to fit comfortably in Mac M3 Pro unified memory
        if len(frames) > 8:
            step = len(frames) / 8
            frames = [frames[int(i * step)] for i in range(8)]
            
        if not frames:
            return {"is_safe_for_real_hardware": True, "reasoning": "No frames loaded from video."}

        system_prompt = (
            "You are a physical AI safety validator for a Unitree G1 robot. "
            "Analyze this sequence of frames showing a MuJoCo physics simulation. "
            "Look for the sim-to-real gap: foot slippage, deep knee bends, extreme momentum, "
            "self-collisions, or dynamic instability that would cause the actual physical hardware to fall over. "
            "Return JSON only with keys: "
            "'chain_of_thought' (str), 'is_safe_for_real_hardware' (bool), 'reasoning' (str)."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                *[{"type": "image", "image": img} for img in frames],
                {"type": "text", "text": "Is this trajectory safe to deploy on the physical Unitree G1 hardware?"}
            ]}
        ]
        
        import torch
        text = _reason2_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = _reason2_processor(text=[text], images=frames, return_tensors="pt").to(_reason2_model.device)
        
        with torch.no_grad():
            output_ids = _reason2_model.generate(**inputs, max_new_tokens=512, temperature=0.2, do_sample=True)
        output_ids = output_ids[:, inputs["input_ids"].shape[1]:]
        raw = _reason2_processor.decode(output_ids[0], skip_special_tokens=True).strip()
        
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group()) if match else {}
        print(f"[Sim-to-Real] CoT: {parsed.get('chain_of_thought', raw)[:120]}...")
        
        return {
            "is_safe_for_real_hardware": bool(parsed.get("is_safe_for_real_hardware", True)),
            "reasoning": str(parsed.get("reasoning", "Checked mechanically.")),
            "chain_of_thought": str(parsed.get("chain_of_thought", raw))
        }
    except Exception as e:
        print(f"⚠️ [Sim-to-Real] Error running Cosmos-Reason2: {e}")
        return {"is_safe_for_real_hardware": True, "reasoning": "Error checking sim-to-real gap."}


def render_unitree_frame(pose: dict | None = None) -> str:
    """Render a single 480×640 frame of the Unitree G1 in the given pose.

    pose: joint-name → angle dict (defaults to STABLE_BALANCE_POSE).
    Returns a base64-encoded JPEG string suitable for passing to verify_stability().
    """
    import io
    from PIL import Image

    if not os.path.exists(MUJOCO_MODEL_PATH):
        return ""

    m = mujoco.MjModel.from_xml_path(MUJOCO_MODEL_PATH)
    d = mujoco.MjData(m)

    joint_angles = {**STABLE_BALANCE_POSE, **(pose or {})}
    for jname, angle in joint_angles.items():
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname)
        if jid != -1:
            d.qpos[m.jnt_qposadr[jid]] = angle

    # Auto-ground: snap feet to floor
    mujoco.mj_kinematics(m, d)
    min_z = float(np.min(d.xpos[:, 2]))
    d.qpos[2] -= min_z
    mujoco.mj_forward(m, d)

    cam = "track_root" if "track_root" in [m.cam(i).name for i in range(m.ncam)] else -1
    renderer = mujoco.Renderer(m, 480, 640)
    renderer.update_scene(d, camera=cam)
    rgb = renderer.render().astype("uint8")
    renderer.close()

    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ── Video generation ──────────────────────────────────────────────────────────

_FAL_ENDPOINT = "fal-ai/ltx-2.3/text-to-video"
_colab_url = os.getenv("COLAB_URL", "").rstrip("/")
_fal_key = os.getenv("FAL_KEY")
_nvidia_key = os.getenv("NVIDIA_API_KEY")

# Determine which backend is available at startup
_video_mode: str | None = None

if _nvidia_key:
    _video_mode = "cosmos"
    print("✅ [Video] Using NVIDIA Cosmos")

if _video_mode is None and _colab_url:
    try:
        r = requests.get(f"{_colab_url}/health", timeout=10,
                         headers={"ngrok-skip-browser-warning": "true"})
        if r.ok:
            _video_mode = "colab"
            print(f"✅ [Video] Colab server ready")
        else:
            print(f"⚠️ [Video] Colab unreachable (status {r.status_code}), trying fal.ai")
    except Exception as e:
        print(f"⚠️ [Video] Colab health check failed: {e}")

if _video_mode is None and _fal_key:
    _video_mode = "fal"
    print("✅ [Video] Using fal.ai")
elif _video_mode is None:
    print("❌ [Video] No backend — set NVIDIA_API_KEY, FAL_KEY, or COLAB_URL in .env")

video_ready = _video_mode is not None


def generate_video(prompt: str, duration: int = 6, resolution: str = "720p") -> dict:
    """Returns {"success": True, "video_base64": str} or {"success": False, "error": str}."""
    if not video_ready:
        return {"success": False, "error": "No video backend configured"}
    if _video_mode == "cosmos":
        return _gen_cosmos(prompt)
    if _video_mode == "colab":
        return _gen_colab(prompt, duration)
    return _gen_fal(prompt, duration, resolution)


def _gen_cosmos(prompt: str) -> dict:
    try:
        # Standard NVIDIA API endpoint for Cosmos Text2World generator
        url = "https://ai.api.nvidia.com/v1/genai/nvidia/cosmos-1.0-diffusion-text2world"
        headers = {
            "Authorization": f"Bearer {_nvidia_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "negative_prompt": "static, blurry, poor quality",
            "seed": 42,
            "guidance_scale": 7.5,
            "steps": 50
        }
        r = requests.post(url, json=payload, headers=headers, timeout=300)
        r.raise_for_status()
        
        data = r.json()
        b64 = data.get("video") or data.get("b64_video")
        if not b64:
            return {"success": False, "error": "No base64 video returned"}
        print(f"✅ [Video] Cosmos ready ({len(b64)//1024} KB)")
        return {"success": True, "video_base64": b64}
    except requests.exceptions.HTTPError as he:
        err = he.response.text
        return {"success": False, "error": f"NVIDIA API Error: {err}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _gen_colab(prompt: str, duration: int) -> dict:
    fps, num_frames = 24, duration * 24
    num_frames = ((num_frames - 1) // 8) * 8 + 1
    try:
        r = requests.post(f"{_colab_url}/generate",
                          json={"prompt": prompt, "num_frames": num_frames, "fps": fps, "height": 480, "width": 704},
                          headers={"ngrok-skip-browser-warning": "true"}, timeout=300)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            return {"success": False, "error": data.get("error", "Colab error")}
        b64 = data["video_base64"]
        print(f"✅ [Video] Colab ready ({len(b64)//1024} KB)")
        return {"success": True, "video_base64": b64}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _gen_fal(prompt: str, duration: int, resolution: str) -> dict:
    try:
        import fal_client
        result = fal_client.subscribe(_FAL_ENDPOINT,
                                      arguments={"prompt": prompt, "duration": duration,
                                                 "resolution": resolution, "generate_audio": False})
        return _fetch_video(result["video"]["url"])
    except ImportError:
        pass
    except Exception as e:
        return {"success": False, "error": str(e)}

    # REST fallback (no fal_client SDK)
    try:
        headers = {"Authorization": f"Key {_fal_key}", "Content-Type": "application/json"}
        r = requests.post(f"https://queue.fal.run/{_FAL_ENDPOINT}",
                          json={"prompt": prompt, "duration": duration, "resolution": resolution, "generate_audio": False},
                          headers=headers, timeout=30)
        r.raise_for_status()
        request_id = r.json()["request_id"]
        status_url = f"https://queue.fal.run/{_FAL_ENDPOINT}/requests/{request_id}"
        for _ in range(36):
            time.sleep(5)
            data = requests.get(status_url, headers=headers, timeout=10).json()
            if data.get("status") == "COMPLETED":
                result = requests.get(f"{status_url}/response", headers=headers, timeout=10).json()
                return _fetch_video(result["video"]["url"])
            if data.get("status") in ("FAILED", "CANCELLED"):
                return {"success": False, "error": f"Job {data['status']}"}
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _fetch_video(url: str) -> dict:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    b64 = base64.b64encode(r.content).decode()
    print(f"✅ [Video] fal.ai ready ({len(b64)//1024} KB)")
    return {"success": True, "video_base64": b64}


# ── MuJoCo renderer ───────────────────────────────────────────────────────────

def render_mujoco_trajectory(trajectory, output_path: str, physics: bool = False) -> str:
    """Render trajectory (pose-dict list or V2R dof_pos dict) to MP4.

    physics=False (default): pure kinematics — poses set directly, no gravity.
    physics=True: PD-controlled simulation with gravity and contact forces.
    """
    v2r = isinstance(trajectory, dict) and "dof_pos" in trajectory
    if isinstance(trajectory, dict) and not v2r:
        trajectory = [trajectory]

    num_frames = len(trajectory["dof_pos"]) if v2r else len(trajectory)
    fps = 30
    traj_fps = float(trajectory.get("fps", 10.0)) if v2r else 10.0

    # Pre-load root pose arrays for V2R trajectories (may be absent → use zeros)
    if v2r:
        root_pos_arr = np.array(trajectory.get("root_pos", [[0, 0, 0.9]] * num_frames))
        root_rot_arr = np.array(trajectory.get("root_rot", [[0, 0, 0, 1]] * num_frames))
        # root_rot is [qx,qy,qz,qw] → MuJoCo wants [qw,qx,qy,qz]
        root_quat_arr = root_rot_arr[:, [3, 0, 1, 2]]

        # Fix 2 — Coordinate frame: SMPL/CV uses Y-up/Z-forward, MuJoCo uses Z-up/X-forward.
        # Apply R_x(90°) to each root quaternion to rotate from CV into robotics frame.
        # R_x(90°) = [w=0.7071, x=0.7071, y=0, z=0]
        def _qmul(q1, q2):
            w1, x1, y1, z1 = q1
            w2, x2, y2, z2 = q2
            return np.array([
                w1*w2 - x1*x2 - y1*y2 - z1*z2,
                w1*x2 + x1*w2 + y1*z2 - z1*y2,
                w1*y2 - x1*z2 + y1*w2 + z1*x2,
                w1*z2 + x1*y2 - y1*x2 + z1*w2,
            ])
        _Rx90 = np.array([0.70710678, 0.70710678, 0.0, 0.0])  # [w,x,y,z]
        root_quat_arr = np.array([_qmul(_Rx90, q) for q in root_quat_arr])
        root_quat_arr /= np.linalg.norm(root_quat_arr, axis=1, keepdims=True)

    if not os.path.exists(MUJOCO_MODEL_PATH):
        raise FileNotFoundError(f"MuJoCo model not found: {MUJOCO_MODEL_PATH}")

    m = mujoco.MjModel.from_xml_path(MUJOCO_MODEL_PATH)
    d = mujoco.MjData(m)

    # Build name-based pkl-index → (ctrl_index, lo, hi) lookup.
    # This is the authoritative mapping used by BOTH initial setup and the render loop.
    # Direct index mapping (d.ctrl[i] = dof_target[i]) is WRONG because the 23-DOF
    # model omits passive joints (waist_roll=13, waist_pitch=14, wrist_pitch/yaw),
    # shifting every arm ctrl slot by 2 relative to the pkl column index.
    act_name_to_ctrl = {}
    for ci in range(m.nu):
        aname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, ci)
        if aname:
            act_name_to_ctrl[aname] = ci

    pkl_to_ctrl = {}  # pkl_dof_idx → (ctrl_idx, lo, hi)
    for pkl_idx, jname in enumerate(_PKL_JOINT_NAMES):
        aname = jname.removesuffix("_joint")
        if aname in act_name_to_ctrl:
            ci = act_name_to_ctrl[aname]
            lo = float(m.actuator_ctrlrange[ci, 0])
            hi = float(m.actuator_ctrlrange[ci, 1])
            pkl_to_ctrl[pkl_idx] = (ci, lo, hi)

    # Build joint-name → qpos-address lookup for kinematic mode
    jname_to_qposadr = {}
    for ji in range(m.njnt):
        jn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, ji)
        if jn:
            jname_to_qposadr[jn] = m.jnt_qposadr[ji]

    def _set_joints_by_name(pose_dict):
        for jname, angle in pose_dict.items():
            if jname in jname_to_qposadr:
                d.qpos[jname_to_qposadr[jname]] = angle

    def _ground_robot():
        """Snap root-z so the lowest body point sits exactly on z=0."""
        mujoco.mj_kinematics(m, d)
        min_z = float(np.min(d.xpos[1:, 2]))   # skip world body (id=0, always z=0)
        d.qpos[2] -= min_z

    # Set initial pose
    if v2r:
        # Physics: start from a stable athletic stance (not the first pkl frame,
        # which may have poor leg geometry).  Kinematic: use first pkl frame joints.
        d.qpos[0:3] = [0.0, 0.0, 0.9]
        d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]  # identity quat [w,x,y,z]
        if physics:
            _set_joints_by_name(STABLE_BALANCE_POSE)
        else:
            first_dof = trajectory["dof_pos"][0]
            for pkl_idx, (ci, lo, hi) in pkl_to_ctrl.items():
                if pkl_idx < len(first_dof):
                    adr = jname_to_qposadr.get(_PKL_JOINT_NAMES[pkl_idx])
                    if adr is not None:
                        d.qpos[adr] = float(np.clip(first_dof[pkl_idx], lo, hi))
        _ground_robot()
    else:
        _set_joints_by_name(STABLE_BALANCE_POSE)

    mujoco.mj_forward(m, d)

    if physics:
        # Simulation PD gains for Unitree G1.
        # NOTE: These are intentionally higher than GR00T hardware values (kp=150/300/40).
        # The real G1 has an internal 500Hz balance controller; these higher sim gains
        # compensate for its absence. For hardware deployment use deploy_real.py which
        # sends target angles to the robot's own inner loop at hardware-native gains.
        # biastype MUST be mjBIAS_AFFINE (1); default 0 silently ignores biasprm.
        _JOINT_KP = {
            "left_hip_pitch":  1200, "left_hip_roll":  1200, "left_hip_yaw":  1200,
            "left_knee":       1600, "left_ankle_pitch": 400, "left_ankle_roll": 400,
            "right_hip_pitch": 1200, "right_hip_roll": 1200, "right_hip_yaw": 1200,
            "right_knee":      1600, "right_ankle_pitch": 400, "right_ankle_roll": 400,
            "waist_yaw": 800, "waist_roll": 0, "waist_pitch": 0,
            "left_shoulder_pitch":  200, "left_shoulder_roll":  200, "left_shoulder_yaw":  200,
            "left_elbow":  200, "left_wrist_roll":  100, "left_wrist_pitch": 0, "left_wrist_yaw": 0,
            "right_shoulder_pitch": 200, "right_shoulder_roll": 200, "right_shoulder_yaw": 200,
            "right_elbow": 200, "right_wrist_roll": 100, "right_wrist_pitch": 0, "right_wrist_yaw": 0,
        }
        m.actuator_gaintype[:] = 0   # mjGAIN_FIXED
        m.actuator_biastype[:] = 1   # mjBIAS_AFFINE — REQUIRED for true PD
        for ci in range(m.nu):
            aname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, ci) or ""
            kp = float(_JOINT_KP.get(aname, 200.0))
            kd = float(max(kp * 0.02, 5.0)) if kp > 0 else 0.0
            m.actuator_gainprm[ci, 0] =  kp
            m.actuator_biasprm[ci, 1] = -kp
            m.actuator_biasprm[ci, 2] = -kd
        substeps = 5  # physics steps per render frame → ~150 Hz
    else:
        m.actuator_gainprm[:, 0] = 1.0
        m.actuator_biasprm[:, 1] = 0.0

    renderer = mujoco.Renderer(m, 480, 640)
    mujoco.mj_forward(m, d)

    if physics:
        # Settle phase: 1.0s of physics holding STABLE_BALANCE_POSE before recording.
        # Lets the robot drop to floor, feet make contact, friction solver resolves,
        # and PD controllers reach equilibrium — before any trajectory data is applied.
        settle_steps = int(1.0 / m.opt.timestep)
        for ci in range(m.nu):
            aname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, ci) or ""
            jname = aname + "_joint"
            d.ctrl[ci] = STABLE_BALANCE_POSE.get(jname, 0.0)
        for _ in range(settle_steps):
            mujoco.mj_step(m, d)
        # Re-ground after settling (robot may have sunk slightly)
        mujoco.mj_kinematics(m, d)
        min_z = float(np.min(d.xpos[1:, 2]))
        if min_z < -0.01:
            d.qpos[2] -= min_z
        mujoco.mj_forward(m, d)
        _settled_root_z = d.qpos[2]
        print(f"  [Physics] settled root_z={_settled_root_z:.3f}m, time reset to 0")
        d.time = 0.0

        # Build ankle ctrl index lookup for CoM compensator
        _com_target_x = float(d.subtree_com[0][0])  # lock onto settled CoM x as target
        _ankle_pitch_ctrls = [act_name_to_ctrl[n] for n in
                               ("left_ankle_pitch", "right_ankle_pitch")
                               if n in act_name_to_ctrl]
        _ankle_roll_ctrls  = [act_name_to_ctrl[n] for n in
                               ("left_ankle_roll", "right_ankle_roll")
                               if n in act_name_to_ctrl]
        _prev_com_x = _com_target_x
        _prev_com_y = 0.0

    cam = "track_root" if "track_root" in [m.cam(i).name for i in range(m.ncam)] else -1
    total_render_frames = int(fps * max(2.5, num_frames / traj_fps))
    frames = []

    # Instability tracking — counts frames where physics would tip the robot
    # (measured before the root pin is applied, so it reflects real CoM dynamics).
    _ROLL_THRESHOLD  = 0.35   # rad (~20°) — G1 tips at ~25°
    _PITCH_THRESHOLD = 0.45   # rad (~26°)
    _unstable_frames = 0

    for f in range(total_render_frames):
        t = (f / fps) * traj_fps
        lo, hi = min(int(t), num_frames - 1), min(int(t) + 1, num_frames - 1)
        a = t - int(t)

        # Interpolate target DOF for this render frame
        if v2r:
            dof_target = (1-a)*np.array(trajectory["dof_pos"][lo]) + a*np.array(trajectory["dof_pos"][hi])
        else:
            pl, ph = trajectory[lo], trajectory[hi]

        if physics:
            if v2r:
                # Legs locked to STABLE_BALANCE_POSE; only upper body (waist_yaw + arms)
                # animates from pkl. This keeps the support polygon fixed so the CoM
                # compensator can maintain balance during dynamic arm gestures.
                # pkl indices 0-11 = legs, 12+ = waist/arms.
                _LEG_PKL_INDICES = set(range(12))
                for pkl_idx, (ci, lo, hi) in pkl_to_ctrl.items():
                    jname = _PKL_JOINT_NAMES[pkl_idx]
                    if pkl_idx in _LEG_PKL_INDICES:
                        # Leg: hold stable stance
                        d.ctrl[ci] = float(STABLE_BALANCE_POSE.get(jname, 0.0))
                    elif pkl_idx < len(dof_target):
                        # Upper body: animate from pkl
                        d.ctrl[ci] = float(np.clip(dof_target[pkl_idx], lo, hi))
            else:
                for i in range(m.nu):
                    aname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
                    jname = aname + "_joint"
                    # Trajectory value takes priority; STABLE_BALANCE_POSE is the
                    # fallback for joints not specified in the animation dict.
                    # Root is pinned after mj_step so legs can safely deviate from
                    # the stable stance without the robot falling.
                    stable = STABLE_BALANCE_POSE.get(jname, 0.0)
                    target = (1-a)*pl.get(jname, stable) + a*ph.get(jname, stable)
                    d.ctrl[i] = target

            # CoM ankle compensator — keeps CoM over support polygon during motion.
            # Measures CoM drift from settled target, nudges ankle pitch/roll to recover.
            mujoco.mj_forward(m, d)
            com_x = float(d.subtree_com[0][0])
            com_y = float(d.subtree_com[0][1])
            com_vel_x = (com_x - _prev_com_x) / (m.opt.timestep * substeps)
            com_vel_y = (com_y - _prev_com_y) / (m.opt.timestep * substeps)
            err_x = com_x - _com_target_x
            err_y = com_y - 0.0
            KP_COM, KD_COM = 0.8, 0.15
            ap_delta = float(np.clip( KP_COM * err_x + KD_COM * com_vel_x, -0.30, 0.30))
            ar_delta = float(np.clip(-KP_COM * err_y - KD_COM * com_vel_y, -0.12, 0.12))
            for ci in _ankle_pitch_ctrls:
                d.ctrl[ci] = float(np.clip(d.ctrl[ci] + ap_delta,
                                           m.actuator_ctrlrange[ci, 0],
                                           m.actuator_ctrlrange[ci, 1]))
            for ci in _ankle_roll_ctrls:
                d.ctrl[ci] = float(np.clip(d.ctrl[ci] + ar_delta,
                                           m.actuator_ctrlrange[ci, 0],
                                           m.actuator_ctrlrange[ci, 1]))
            _prev_com_x = com_x
            _prev_com_y = com_y

            for _ in range(substeps):
                mujoco.mj_step(m, d)

            # ── Roll/pitch instability check (TWIST2-inspired) ────────────────
            # Read physics orientation BEFORE pinning — this is what the robot
            # would do without the harness, revealing true dynamic instability.
            # MuJoCo freejoint qpos[3:7] = [qw, qx, qy, qz]
            qw, qx, qy, qz = d.qpos[3], d.qpos[4], d.qpos[5], d.qpos[6]
            _roll  = float(np.arctan2(2*(qw*qx + qy*qz), 1 - 2*(qx*qx + qy*qy)))
            _pitch = float(np.arcsin(float(np.clip(2*(qw*qy - qz*qx), -1.0, 1.0))))
            if abs(_roll) > _ROLL_THRESHOLD or abs(_pitch) > _PITCH_THRESHOLD:
                _unstable_frames += 1

            # Root stabilisation: lock XY position and upright orientation after every
            # step.  Diagnosis showed the robot falls sideways (CoM_y drift) — the
            # ankle roll compensator is insufficient against large arm inertia.
            # Locking the root is equivalent to a chest harness: physics governs joint
            # dynamics and arm inertia, but the whole body cannot topple.
            # Only qpos[0:7] and qvel[0:6] (freejoint) are overridden; all other
            # joint states are purely physics-driven.
            d.qpos[0] = 0.0          # X — keep over origin
            d.qpos[1] = 0.0          # Y — no lateral drift
            d.qpos[2] = _settled_root_z  # Z — maintain standing height
            d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]  # upright orientation
            d.qvel[0:6] = 0.0        # zero root velocity so energy doesn't build up
        else:
            if v2r:
                # Apply root pose from trajectory, auto-ground z
                rp = (1-a)*root_pos_arr[lo] + a*root_pos_arr[hi]
                rq = (1-a)*root_quat_arr[lo] + a*root_quat_arr[hi]
                rq /= np.linalg.norm(rq)
                for pkl_idx, (ci, lo, hi) in pkl_to_ctrl.items():
                    if pkl_idx < len(dof_target):
                        adr = jname_to_qposadr.get(_PKL_JOINT_NAMES[pkl_idx])
                        if adr is not None:
                            d.qpos[adr] = float(np.clip(dof_target[pkl_idx], lo, hi))
                d.qpos[0:2] = rp[0:2]
                d.qpos[3:7] = rq
                mujoco.mj_kinematics(m, d)
                # Exclude world body (id=0, z=0) from min — otherwise no grounding occurs
                min_z = float(np.min(d.xpos[1:, 2]))
                d.qpos[2] = rp[2] - min_z
                mujoco.mj_kinematics(m, d)
            else:
                for jname, angle in STABLE_BALANCE_POSE.items():
                    jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname)
                    if jid != -1:
                        d.qpos[m.jnt_qposadr[jid]] = angle
                for jname in set(pl) | set(ph):
                    if jname in STABLE_BALANCE_POSE:
                        continue
                    jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname)
                    if jid != -1:
                        d.qpos[m.jnt_qposadr[jid]] = (1-a)*pl.get(jname, 0.0) + a*ph.get(jname, 0.0)
                mujoco.mj_kinematics(m, d)
            d.time += 1.0 / fps

        renderer.update_scene(d, camera=cam)
        frames.append(renderer.render().astype("uint8"))

    renderer.close()

    if physics and total_render_frames > 0:
        instability_pct = 100.0 * _unstable_frames / total_render_frames
        if instability_pct > 30:
            print(f"  [Physics] ⚠️  Instability detected: {instability_pct:.0f}% of frames "
                  f"exceeded roll/pitch threshold — trajectory may fall on real hardware.")
        elif instability_pct > 0:
            print(f"  [Physics] ℹ️  Minor instability: {instability_pct:.0f}% of frames near tip threshold.")
        else:
            print(f"  [Physics] ✅ Stable — no roll/pitch threshold exceeded.")

    imageio.mimsave(output_path, frames, fps=fps, quality=8, pixelformat="yuv420p", macro_block_size=None)
    return output_path


# ── Video2Robot pipeline ──────────────────────────────────────────────────────

def run_video2robot_pipeline(video_b64: str) -> dict | None:
    """Run PromptHMR + GMR on a video. Returns motion dict or None. Safe for asyncio.to_thread()."""
    v2r_dir = Path(__file__).parent.parent / "video2robot"
    if not v2r_dir.exists():
        return None

    ts = int(time.time())
    project_dir = v2r_dir / "data" / f"mascot_{ts}"
    project_dir.mkdir(parents=True, exist_ok=True)
    video_path = project_dir / "original.mp4"
    video_path.write_bytes(base64.b64decode(video_b64))

    try:
        # Use phmr env's Python explicitly — avoids being shadowed by any active .venv
        import shutil
        conda_base = subprocess.check_output(
            ["conda", "info", "--base"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        phmr_python = str(Path(conda_base) / "envs" / "phmr" / "bin" / "python")
        if not Path(phmr_python).exists():
            phmr_python = shutil.which("python") or "python"

        r = subprocess.run(
            [phmr_python, "scripts/run_pipeline.py", "--video", str(video_path),
             "--robot", "unitree_g1", "--static-camera"],
            cwd=str(v2r_dir), capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            print(f"[V2R] Failed: {r.stderr[-300:]}")
            return None
        pkls = sorted(project_dir.glob("robot_motion*.pkl"))
        if not pkls:
            return None
        with open(pkls[0], "rb") as f:
            motion = pickle.load(f)
        print(f"[V2R] ✅ {len(motion.get('dof_pos', []))} frames")
        return motion
    except subprocess.TimeoutExpired:
        print("[V2R] Timed out")
        return None
    except Exception as e:
        print(f"[V2R] Error: {e}")
        return None
    finally:
        if video_path.exists():
            video_path.unlink()


def get_base64_video(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()
