"""
mujoco_physics_eval.py — Physics-Grounded G1 Pose Evaluator
------------------------------------------------------------
Replaces mujoco_preview.py's `mj_kinematics()` with a real physics integrator
(`mj_step()`) so that ZMP failures, CoM shifts, and balance loss are observable.

The G1 23-DOF model (scene.xml) has 29 actuators driven as torque motors.
This script implements a PD controller in Python:
    tau[i] = Kp * (q_target[i] - q[i]) - Kd * dq[i]
    data.ctrl[i] = clip(tau[i], ctrlrange[i])

FALSIFICATION BASELINE:
    Run with no flags. The robot should hold STABLE_BALANCE_POSE upright for 5s.
    If it sags and falls → the hand-crafted angles in hero_pose.py are not
    physically grounded and must be re-derived.

Usage:
    python mujoco_physics_eval.py                          # baseline hold
    python mujoco_physics_eval.py --animation wave         # arm wave
    python mujoco_physics_eval.py --animation hulk_smash   # dynamic smash
    python mujoco_physics_eval.py --animation iron_man_repulsor
    python mujoco_physics_eval.py --animation spider_man_web_shoot
    python mujoco_physics_eval.py --list                   # list all animations
    python mujoco_physics_eval.py --hold 10               # hold baseline for 10s

Available animations (from hero_pose.py):
    wave, flex, punch, hulk_smash, iron_man_repulsor,
    spider_man_web_shoot, spider_man_landing, captain_america_shield,
    thor_lightning, wolverine_claws
"""

import argparse
import sys
import time
import numpy as np
import mujoco
import mujoco.viewer
from pathlib import Path
import requests
import pickle

# ─── IMPORT HERO POSES ────────────────────────────────────────────────────────
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

ANIMATION_REGISTRY = {
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

# ─── MODEL PATH ───────────────────────────────────────────────────────────────
SCENE_XML = (
    Path(__file__).parent.parent
    / "kim_workspace" / "hardware_deployment"
    / "unitree_mujoco" / "unitree_robots" / "g1" / "scene.xml"
)

# ─── PHYSICS CONSTANTS ────────────────────────────────────────────────────────
# Confirmed from MuJoCo model introspection (mujoco.MjModel):
#   model.nu = 29 (not 23 — the filename is misleading)
#   model.opt.timestep = 0.002s (already safe for 35kg biped)

# PD gains — matching CLAUDE.md physics mode (kp=200, kd=10)
# Applied uniformly; clipped per-joint by ctrlrange from XML.
KP = 200.0
KD = 10.0

# Initial pelvis height: measured with STABLE_BALANCE_POSE + mj_forward
# (default zero-pose qpos[2]=0.793; after Z-fold crouch = 0.787)
ROOT_Z_INIT = 0.787

# Fall detection threshold (pelvis Z below this = fallen)
FALLEN_THRESHOLD = 0.4

# Control loop: 500 Hz physics, 50 Hz viewer
PHYSICS_DT  = 0.002   # must match model.opt.timestep
VIEWER_HZ   = 50
STEPS_PER_VIEWER = int(round(1.0 / (VIEWER_HZ * PHYSICS_DT)))  # = 10

# Hero pose animation: 10 FPS → 1 frame every 5 viewer syncs
ANIMATION_FPS        = 10
VIEWER_FRAMES_PER_ANIM_FRAME = int(round(VIEWER_HZ / ANIMATION_FPS))  # = 5

# Diagnostic print interval
DIAG_INTERVAL_SEC = 0.5

# VLAW constants
FALL_CONFIRM_TICKS = 25                                         # physics ticks before VLAW fires (~0.05s)
VLAW_SERVER_URL    = "http://127.0.0.1:8080/vlaw_sim_sync"
CRASH_STATE_PATH   = Path(__file__).parent / "crash_state.json"


# ─── JOINT MAPPING (built at runtime from model — never hardcoded) ─────────────

def build_joint_maps(model: mujoco.MjModel) -> tuple[dict, np.ndarray, np.ndarray]:
    """
    Returns:
        name_to_ctrl : joint_name → ctrl_index  (for pose_dict → ctrl array)
        qpos_idx     : (nu,) array of qpos addresses indexed by ctrl channel
        qvel_idx     : (nu,) array of qvel addresses indexed by ctrl channel
    All 29 actuators in g1_23dof are joint-type so every ctrl index is covered.
    """
    name_to_ctrl = {}
    qpos_list = [0] * model.nu
    qvel_list = [0] * model.nu

    for i in range(model.nu):
        if model.actuator_trntype[i] != mujoco.mjtTrn.mjTRN_JOINT:
            continue
        trnid = model.actuator_trnid[i, 0]
        jname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, trnid)
        name_to_ctrl[jname] = i
        qpos_list[i] = int(model.jnt_qposadr[trnid])
        qvel_list[i] = int(model.jnt_dofadr[trnid])

    return name_to_ctrl, np.array(qpos_list), np.array(qvel_list)


def pose_dict_to_target(
    pose: dict,
    name_to_ctrl: dict,
    qpos_idx: np.ndarray,
    data: mujoco.MjData,
) -> np.ndarray:
    """
    Converts a hero_pose dict {joint_name: angle_rad} into a dense (nu,) target
    array. Joints absent from the pose dict hold their current qpos value.
    """
    targets = data.qpos[qpos_idx].copy()
    for jname, angle in pose.items():
        if jname in name_to_ctrl:
            targets[name_to_ctrl[jname]] = angle
    return targets


def apply_pd(
    data: mujoco.MjData,
    targets: np.ndarray,
    qpos_idx: np.ndarray,
    qvel_idx: np.ndarray,
    ctrl_lo: np.ndarray,
    ctrl_hi: np.ndarray,
):
    """Write PD torques into data.ctrl. Vectorized over all 29 joints."""
    q  = data.qpos[qpos_idx]
    dq = data.qvel[qvel_idx]
    data.ctrl[:] = np.clip(KP * (targets - q) - KD * dq, ctrl_lo, ctrl_hi)


# ─── ROOT STATE DIAGNOSTICS ───────────────────────────────────────────────────

def root_diagnostics(data: mujoco.MjData) -> dict:
    """Extract pelvis Z and Euler roll/pitch from free-joint state."""
    root_z = data.qpos[2]

    # Free joint quaternion: qpos[3:7] = (w, x, y, z)
    qw, qx, qy, qz = data.qpos[3], data.qpos[4], data.qpos[5], data.qpos[6]
    # Roll (x-axis rotation)
    sinr = 2.0 * (qw * qx + qy * qz)
    cosr = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll  = np.arctan2(sinr, cosr)
    # Pitch (y-axis rotation)
    sinp = 2.0 * (qw * qy - qz * qx)
    pitch = np.arcsin(np.clip(sinp, -1.0, 1.0))

    return {"z": root_z, "roll": roll, "pitch": pitch}


def compute_tracking_error(
    data: mujoco.MjData,
    targets: np.ndarray,
    qpos_idx: np.ndarray,
) -> float:
    """RMS joint-angle tracking error across all actuated joints."""
    errors = targets - data.qpos[qpos_idx]
    return float(np.sqrt(np.mean(errors ** 2)))


def pkl_to_target_list(pkl_path: str, nu: int) -> list[np.ndarray]:
    """
    Load (N, 35) joint angles from a pkl file.
    Returns list of (nu,) float32 target arrays for apply_pd().
    Hardware IDL motor index i maps directly to ctrl channel i for i in 0..nu-1.
    Indices nu..34 are extended joints absent from the model and are discarded.
    """
    with open(pkl_path, "rb") as f:
        raw = pickle.load(f)
    joints = np.array(raw["joint_angles"], dtype=np.float32)  # (N, 35)
    return [row[:nu].copy() for row in joints]


# ─── INITIALIZATION ───────────────────────────────────────────────────────────

def seed_initial_state(
    data: mujoco.MjData,
    model: mujoco.MjModel,
    name_to_ctrl: dict,
    qpos_idx: np.ndarray,
):
    """
    Seed data.qpos with STABLE_BALANCE_POSE before the first physics step.
    Without this, zero-radian initialization drops the robot instantly under gravity.
    """
    data.qpos[:7] = [0.0, 0.0, ROOT_Z_INIT, 1.0, 0.0, 0.0, 0.0]  # xyz + quat (upright)
    for jname, angle in STABLE_BALANCE_POSE.items():
        if jname in name_to_ctrl:
            data.qpos[qpos_idx[name_to_ctrl[jname]]] = angle
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)


# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

def run(animation_name: str | None = None, hold_seconds: float = 5.0,
        vlaw: bool = False, fall_test: bool = False):
    if not SCENE_XML.exists():
        print(f"[ERROR] scene.xml not found at:\n  {SCENE_XML}")
        print("Expected path: kim_workspace/hardware_deployment/unitree_mujoco/unitree_robots/g1/scene.xml")
        sys.exit(1)

    print(f"Loading: {SCENE_XML.name}")
    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    data  = mujoco.MjData(model)

    # Verify model parameters
    assert model.nu == 29, f"Expected 29 actuators, got {model.nu}"
    assert abs(model.opt.timestep - PHYSICS_DT) < 1e-6, (
        f"Model timestep {model.opt.timestep} ≠ expected {PHYSICS_DT}"
    )
    print(f"Model confirmed: nu={model.nu}, dt={model.opt.timestep}s")

    # Build runtime joint maps
    name_to_ctrl, qpos_idx, qvel_idx = build_joint_maps(model)
    ctrl_lo = model.actuator_ctrlrange[:, 0].copy()
    ctrl_hi = model.actuator_ctrlrange[:, 1].copy()

    # Seed initial state
    seed_initial_state(data, model, name_to_ctrl, qpos_idx)
    print(f"Initial root Z: {data.qpos[2]:.4f}m (target={ROOT_Z_INIT}m)")

    # Build trajectory: [hold phase] + [animation frames] + [return to stable]
    trajectory: list[dict] = []

    # Phase 0: hold STABLE_BALANCE_POSE for hold_seconds
    hold_frames = int(hold_seconds * ANIMATION_FPS)
    trajectory += [STABLE_BALANCE_POSE] * hold_frames

    # Phase 1: animation (if specified)
    if animation_name:
        anim_frames = ANIMATION_REGISTRY[animation_name]()
        trajectory += anim_frames
        print(f"Animation: {animation_name} ({len(anim_frames)} frames @ {ANIMATION_FPS}fps)")
        # Phase 2: return to stable
        trajectory += [STABLE_BALANCE_POSE] * int(2.0 * ANIMATION_FPS)

    total_duration = len(trajectory) / ANIMATION_FPS
    print(f"Total trajectory: {len(trajectory)} frames ({total_duration:.1f}s)")
    print(f"\n{'='*60}")
    print("FALSIFICATION BASELINE: Does the G1 hold STABLE_BALANCE_POSE?")
    print("If root Z drops below 0.4m → pose is NOT physically grounded.")
    print(f"{'='*60}\n")

    anim_frame_idx    = 0
    prev_frame_idx    = -1
    current_target    = pose_dict_to_target(trajectory[0], name_to_ctrl, qpos_idx, data)
    viewer_tick       = 0
    last_diag_time    = time.monotonic()
    fallen            = False
    fall_tick_count   = 0
    vlaw_fired        = False

    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.lookat[:] = [0.0, 0.0, 0.8]
        viewer.cam.distance  = 3.5
        viewer.cam.elevation = -15

        while viewer.is_running() and anim_frame_idx < len(trajectory):
            step_start = time.monotonic()

            # ── Recompute target only when animation frame advances (10 Hz) ────
            if anim_frame_idx != prev_frame_idx:
                frame_data = trajectory[anim_frame_idx]
                
                # Check for PKL playback array mode
                if "_pkl_array" in frame_data:
                    pkl_row = frame_data["_pkl_array"]
                    size = min(len(pkl_row), len(current_target))
                    current_target[:size] = pkl_row[:size]
                else:
                    current_target = pose_dict_to_target(
                        frame_data, name_to_ctrl, qpos_idx, data
                    )
                prev_frame_idx = anim_frame_idx

            # ── Physics steps (10 steps per viewer frame) ─────────────────────
            for _ in range(STEPS_PER_VIEWER):
                apply_pd(data, current_target, qpos_idx, qvel_idx, ctrl_lo, ctrl_hi)
                mujoco.mj_step(model, data)

            # ── Diagnostics ───────────────────────────────────────────────────
            diag = root_diagnostics(data)
            err  = compute_tracking_error(data, current_target, qpos_idx)

            now = time.monotonic()
            if now - last_diag_time >= DIAG_INTERVAL_SEC:
                last_diag_time = now
                sim_time = data.time
                phase = "HOLD" if anim_frame_idx < hold_frames else animation_name or "HOLD"
                
                # If we are in extended PKL mode, relabel phase
                if anim_frame_idx >= hold_frames and "_pkl_array" in trajectory[anim_frame_idx]:
                    phase = "VLAW_RECOVERY"

                status = "STANDING" if diag["z"] > FALLEN_THRESHOLD else "*** FALLEN ***"
                print(
                    f"t={sim_time:6.2f}s  [{phase:<22}]  "
                    f"Z={diag['z']:.4f}m  "
                    f"roll={np.degrees(diag['roll']):+6.2f}°  "
                    f"pitch={np.degrees(diag['pitch']):+6.2f}°  "
                    f"RMS_err={err:.4f}rad  "
                    f"[{status}]"
                )

            # ── fall-test: cut PD for 15 viewer frames after hold phase ─────────
            if fall_test and not vlaw_fired and anim_frame_idx == hold_frames:
                current_target = np.zeros(model.nu)

            # ── VLAW fall watcher ─────────────────────────────────────────────
            if vlaw and not vlaw_fired:
                if diag["z"] < FALLEN_THRESHOLD:
                    fall_tick_count += 1
                    if fall_tick_count >= FALL_CONFIRM_TICKS:
                        vlaw_fired = True
                        fallen = True
                        print(f"\n[VERDICT] FALLEN at t={data.time:.2f}s, Z={diag['z']:.4f}m")
                        crash = {
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "failure_reason": f"Z={diag['z']:.3f}m below threshold",
                            "telemetry_buffer": [{"base_height": float(diag["z"]),
                                                  "qpos": data.qpos[:7].tolist()}],
                        }
                        CRASH_STATE_PATH.write_text(__import__("json").dumps(crash, indent=2))
                        print(f"[VLAW] Crash state → {CRASH_STATE_PATH.name}")
                        try:
                            res = requests.post(VLAW_SERVER_URL, json=crash, timeout=5.0)
                            if res.status_code == 200:
                                pkl_path = res.json().get("recovery_pkl", "")
                                print(f"[VLAW] Server returned recovery pkl: {pkl_path}")
                                if Path(pkl_path).exists():
                                    recovery = pkl_to_target_list(pkl_path, model.nu)
                                    print(f"[VLAW] Recovery loaded: {len(recovery)} frames")
                                    for row in recovery:
                                        trajectory.append({"_pkl_array": row})
                                    fallen = False
                                else:
                                    print(f"[VLAW] pkl path not found on disk: {pkl_path}")
                            else:
                                print(f"[VLAW] Server error {res.status_code}")
                        except Exception as e:
                            print(f"[VLAW] POST failed: {e}")
                else:
                    fall_tick_count = 0

            # ── Viewer sync ───────────────────────────────────────────────────
            viewer.sync()
            viewer_tick += 1

            # ── Advance animation frame ───────────────────────────────────────
            if viewer_tick % VIEWER_FRAMES_PER_ANIM_FRAME == 0:
                anim_frame_idx += 1

            # ── Real-time pacing ──────────────────────────────────────────────
            elapsed = time.monotonic() - step_start
            sleep_t = (1.0 / VIEWER_HZ) - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    # ── Final verdict ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    final_diag = root_diagnostics(data)
    if fallen:
        print(f"RESULT: FAILED — Robot fell during evaluation.")
        print(f"Final Z = {final_diag['z']:.4f}m")
    else:
        print(f"RESULT: PASSED — Robot held upright for full trajectory.")
        print(f"Final Z = {final_diag['z']:.4f}m  "
              f"(Δ from init = {final_diag['z'] - ROOT_Z_INIT:+.4f}m)")
        if animation_name:
            print(f"Action: '{animation_name}' animation is physically viable in MuJoCo.")
        else:
            print("Next: run with --animation <name> to test dynamic poses.")
    print(f"{'='*60}\n")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Physics-grounded G1 pose evaluator (mj_step + PD control)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--animation", "-a",
        choices=list(ANIMATION_REGISTRY.keys()),
        help="Hero animation to test after holding STABLE_BALANCE_POSE",
    )
    group.add_argument(
        "--list", action="store_true",
        help="List all available animations and exit",
    )
    parser.add_argument(
        "--hold", type=float, default=5.0,
        help="Seconds to hold STABLE_BALANCE_POSE before animation (default: 5.0)",
    )
    parser.add_argument(
        "--vlaw", action="store_true",
        help="Enable VLAW fall detection and recovery loop (requires server.py running)",
    )
    parser.add_argument(
        "--fall-test", action="store_true",
        help="Cut PD after hold phase to induce a controlled fall for VLAW testing",
    )
    args = parser.parse_args()

    if args.list:
        print("Available animations:")
        for name in sorted(ANIMATION_REGISTRY.keys()):
            frames = ANIMATION_REGISTRY[name]()
            duration = len(frames) / ANIMATION_FPS
            print(f"  {name:<30} ({len(frames)} frames, {duration:.1f}s)")
        return

    run(animation_name=args.animation, hold_seconds=args.hold,
        vlaw=args.vlaw, fall_test=args.fall_test)


if __name__ == "__main__":
    main()
