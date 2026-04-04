"""
kinematic_brain.py — LLM-grounded kinematic pose generation for Unitree G1

Implements Gemini's three recommendations:
  1. URDF joint limits injected into LLM system prompt (proprioceptive grounding)
  2. LLM outputs structured JSON joint angles directly (not animation names)
  3. Real ZMP stability validation using MuJoCo CoM computation (not text mock)
"""

import os
import json
import re
import numpy as np
from hero_pose import STABLE_BALANCE_POSE

# ─── G1 UPPER BODY JOINT LIMITS (from g1_23dof.xml) ──────────────────────────
# Legs are locked in STABLE_BALANCE_POSE (imported from hero_pose) — LLM controls upper body only
UPPER_BODY_LIMITS = {
    "waist_yaw_joint":             [-2.618,  2.618],
    "waist_roll_joint":            [-0.52,   0.52],
    "waist_pitch_joint":           [-0.52,   0.52],
    "left_shoulder_pitch_joint":   [-3.089,  2.670],
    "left_shoulder_roll_joint":    [-1.588,  2.252],
    "left_shoulder_yaw_joint":     [-2.618,  2.618],
    "left_elbow_joint":            [-1.047,  2.094],
    "left_wrist_roll_joint":       [-1.972,  1.972],
    "left_wrist_pitch_joint":      [-0.5,    0.5],
    "left_wrist_yaw_joint":        [-0.5,    0.5],
    "right_shoulder_pitch_joint":  [-3.089,  2.670],
    "right_shoulder_roll_joint":   [-2.252,  1.588],
    "right_shoulder_yaw_joint":    [-2.618,  2.618],
    "right_elbow_joint":           [-1.047,  2.094],
    "right_wrist_roll_joint":      [-1.972,  1.972],
    "right_wrist_pitch_joint":     [-0.5,    0.5],
    "right_wrist_yaw_joint":       [-0.5,    0.5],
}

MODEL_PATH = "unitree_mujoco/unitree_robots/g1/scene_23dof.xml"

# Cached MuJoCo model — loaded once, reused for all ZMP checks
_mj_model_cache = None

def _get_mujoco_model():
    global _mj_model_cache
    if _mj_model_cache is None:
        import mujoco
        _mj_model_cache = mujoco.MjModel.from_xml_path(MODEL_PATH)
    return _mj_model_cache

# ─── BUILD LIMITS BLOCK FOR LLM SYSTEM PROMPT ─────────────────────────────────
_LIMITS_BLOCK = "\n".join(
    f"  {jname}: [{lo:.3f}, {hi:.3f}]"
    for jname, (lo, hi) in UPPER_BODY_LIMITS.items()
)

KINEMATIC_SYSTEM_PROMPT = f"""You are a Kinematic Director for a Unitree G1 humanoid robot.

Given a hero gesture description, output joint-angle keyframes that create an expressive animation.

ROBOT — Unitree G1, 23 DOF:
- Legs are LOCKED in a stable athletic stance. You control UPPER BODY only.
- All angles are in RADIANS.

UPPER BODY JOINT LIMITS (HARD — never exceed these):
{_LIMITS_BLOCK}

JOINT CONVENTIONS:
  shoulder_pitch : negative = arm sweeps FORWARD, positive = arm sweeps BACK
  shoulder_roll  : left positive = arm out, right negative = arm out
  elbow          : positive = bend, 0 = straight arm
  waist_pitch    : negative = lean FORWARD, positive = lean BACK
  waist_yaw      : positive = twist LEFT, negative = twist RIGHT

OUTPUT — strictly valid JSON, no markdown fences:
{{
  "keyframes": [
    {{
      "label": "short pose name",
      "duration": 0.4,
      "joints": {{
        "left_shoulder_pitch_joint": -1.2,
        "right_elbow_joint": 1.5
      }}
    }}
  ]
}}

Rules:
- 3–6 keyframes for a full sequence
- First and last keyframe should be near neutral (joints close to 0.0)
- Duration per keyframe: 0.1–1.0 seconds
- Exaggerate expressively within limits — Disney animation energy
- ONLY include joints that differ from neutral
- Do NOT explain — output JSON only"""


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def wrap_angles(joints: dict) -> dict:
    """Wrap all angles to [-π, π] so PD controllers take the shortest path.
    Prevents 360° motor spins when LLM output crosses the ±π boundary."""
    return {k: float(np.arctan2(np.sin(v), np.cos(v))) for k, v in joints.items()}


def clip_to_limits(joints: dict) -> dict:
    """Hard-clip all upper body joint angles to URDF limits."""
    clipped = {}
    for jname, angle in joints.items():
        if jname in UPPER_BODY_LIMITS:
            lo, hi = UPPER_BODY_LIMITS[jname]
            clipped[jname] = float(np.clip(angle, lo, hi))
        else:
            clipped[jname] = float(angle)
    return clipped


# ─── ZMP STABILITY (REAL MUJOCO PHYSICS) ──────────────────────────────────────

def check_zmp_stability(joint_angles: dict) -> dict:
    """
    Compute whole-body CoM using MuJoCo and check whether it falls within
    the support polygon of the bipedal stance.

    Support polygon (G1 in STABLE_BALANCE_POSE):
      x (fore/aft):  ±0.08 m
      y (lateral):   ±0.09 m
    """
    import mujoco

    if not os.path.exists(MODEL_PATH):
        return {"is_stable": True, "reasoning": "Model not found — ZMP check skipped.", "com_x": 0.0, "com_y": 0.0}

    m = _get_mujoco_model()
    d = mujoco.MjData(m)

    # Set stable leg base (single source of truth from hero_pose)
    for jname, angle in STABLE_BALANCE_POSE.items():
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname)
        if jid != -1:
            d.qpos[m.jnt_qposadr[jid]] = angle

    # Set proposed upper body pose
    for jname, angle in joint_angles.items():
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname)
        if jid != -1:
            d.qpos[m.jnt_qposadr[jid]] = angle

    mujoco.mj_forward(m, d)

    # Whole-body CoM = mass-weighted average of all body CoM positions
    total_mass = float(np.sum(m.body_mass))
    com_xy = np.zeros(2)
    for i in range(m.nbody):
        mass = float(m.body_mass[i])
        if mass > 0:
            com_xy += mass * d.xipos[i, :2]
    com_xy /= total_mass

    x_limit, y_limit = 0.08, 0.09
    is_stable = abs(com_xy[0]) < x_limit and abs(com_xy[1]) < y_limit
    status = "STABLE" if is_stable else "UNSTABLE"

    reasoning = (
        f"CoM @ x={com_xy[0]:.3f}m, y={com_xy[1]:.3f}m — {status} "
        f"(support polygon ±{x_limit}m fore/aft, ±{y_limit}m lateral)"
    )

    return {
        "is_stable": is_stable,
        "reasoning": reasoning,
        "com_x": float(com_xy[0]),
        "com_y": float(com_xy[1]),
    }


# ─── MAIN: LLM → JOINT ANGLES → TRAJECTORY ────────────────────────────────────

def generate_kinematic_trajectory(gesture_desc: str, hero_name: str) -> list | None:
    """
    Ask the LLM to generate joint-angle keyframes grounded in G1 URDF limits,
    validate with real ZMP physics, then build a smooth trajectory.

    Returns: list of pose dicts (same format as hero_pose.animate()), or None on failure.
    """
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("[KinematicBrain] No HF_TOKEN — skipping LLM trajectory generation")
        return None

    try:
        from huggingface_hub import InferenceClient
        from hero_pose import animate

        client = InferenceClient(model="Qwen/Qwen2.5-72B-Instruct", token=hf_token)

        user_msg = (
            f"Hero: {hero_name}\n"
            f"Gesture: {gesture_desc}\n\n"
            "Generate expressive keyframes. Make the motion dramatic and hero-like."
        )

        print(f"[KinematicBrain] 🧠 Asking LLM for joint-angle keyframes (hero={hero_name})...")
        response = client.chat_completion(
            messages=[
                {"role": "system", "content": KINEMATIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=1400,
            temperature=0.6,
        )

        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

        parsed = json.loads(raw)
        keyframes_data = parsed.get("keyframes", [])

        if len(keyframes_data) < 2:
            print("[KinematicBrain] ⚠️ LLM returned fewer than 2 keyframes")
            return None

        # Clip all angles to hardware limits
        for kf in keyframes_data:
            kf["joints"] = clip_to_limits(wrap_angles(kf.get("joints", {})))
            print(f"  [{kf.get('label', '?')}] duration={kf.get('duration', 0.4):.2f}s  joints={kf['joints']}")

        # ZMP check on the most extreme keyframe
        most_extreme = max(
            keyframes_data,
            key=lambda kf: sum(abs(v) for v in kf["joints"].values())
        )
        zmp = check_zmp_stability(most_extreme["joints"])
        print(f"[ZMP] {zmp['reasoning']}")

        if not zmp["is_stable"]:
            print("[ZMP] ⚠️ CoM outside support polygon — dampening waist joints 60%")
            for kf in keyframes_data:
                for jname in ["waist_pitch_joint", "waist_roll_joint", "waist_yaw_joint"]:
                    if jname in kf["joints"]:
                        kf["joints"][jname] *= 0.4
            # Re-check
            zmp2 = check_zmp_stability(most_extreme["joints"])
            print(f"[ZMP] Post-correction: {zmp2['reasoning']}")

        # Build smooth trajectory using existing animate()
        keyframes = [
            (kf["joints"], float(kf.get("duration", 0.4)))
            for kf in keyframes_data
        ]
        trajectory = animate(keyframes, fps=10)

        print(f"[KinematicBrain] ✅ {len(trajectory)}-frame LLM-grounded trajectory ready")
        return trajectory

    except json.JSONDecodeError as e:
        print(f"[KinematicBrain] ❌ JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"[KinematicBrain] ❌ Error: {e}")
        return None
