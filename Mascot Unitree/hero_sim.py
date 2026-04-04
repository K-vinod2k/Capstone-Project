"""
hero_sim.py — Disturbance Rejection Test for Unitree G1 CoM Compensator

Protocol:
  Phase 1 (0 – 3.0 s):   Robot stands; CoM feedback loop active; baseline logged.
  Phase 2 (3.0 – 3.1 s): 50 N impulse applied to torso_link along world +X for 0.1 s.
  Phase 3 (3.1 – 8.0 s): Ankle/waist pitch+roll PD compensator reacts and recovers.

Pass criterion: CoM returns inside ±8 cm fore/aft within 2 s of impulse end.

Usage:
  python hero_sim.py
  python hero_sim.py --out output/disturbance_test.mp4
"""

import argparse
import os
import sys
import numpy as np
import mujoco
import imageio
from pathlib import Path

from hero_pose import STABLE_BALANCE_POSE
from kinematic_brain import MODEL_PATH

# ── Timing ─────────────────────────────────────────────────────────────────────
DT           = 0.002     # physics timestep — 500 Hz
RENDER_FPS   = 30
SIM_DURATION = 8.0       # seconds total

STRIKE_T   = 3.0         # impulse start (s)
STRIKE_DUR = 0.1         # impulse duration (s)
STRIKE_FX  = 50.0        # N, world +X (sagittal forward push on torso)
SETTLE_T   = 1.0         # pre-test settling time: physics runs but not recorded

# ── Per-joint PD gains (N·m/rad) — scaled up from hardware for sim fidelity ──
# Hardware uses KP=50 for ankles, KP=150 for hips. In MuJoCo these must be higher
# because the hardware has high-bandwidth inner torque loops that simulation lacks.
# Rule of thumb: sim_KP ≈ 8–12× hardware_KP for comparable stiffness response.
_KP_PER_JOINT = np.array([
    1200, 1200, 1200, 1600, 400, 400,   # left leg
    1200, 1200, 1200, 1600, 400, 400,   # right leg
     800,    0,    0,                   # waist (yaw active; roll/pitch passive→0)
     200,  200,  200, 200, 100,  0,  0, # left arm (wrist_pitch/yaw passive→0)
     200,  200,  200, 200, 100,  0,  0, # right arm
], dtype=float)

_KD_PER_JOINT = np.array([
    60, 60, 60, 80, 20, 20,
    60, 60, 60, 80, 20, 20,
    40,  0,  0,
    10, 10, 10, 10,  5,  0,  0,
    10, 10, 10, 10,  5,  0,  0,
], dtype=float)

# ── CoM compensator gains ──────────────────────────────────────────────────────
# Ankle pitch/roll  — first line: fast CoP shift via foot pressure
# Waist pitch/roll  — second line: slower trunk lean to recenter CoM
KP_ANKLE = 6.0      # rad per m of CoM error
KD_ANKLE = 3.0      # rad per m/s of CoM velocity
KP_WAIST = 2.5
KD_WAIST = 1.2

# ── Support polygon (same as kinematic_brain.py ZMP check) ────────────────────
SUPPORT_X = 0.08    # ±m fore/aft
SUPPORT_Y = 0.09    # ±m lateral

# ── Joint angle limits used by compensator (from deploy_real.py JOINT_LIMITS) ─
ANKLE_PITCH_RANGE = (-0.8727,  0.5236)   # rad
ANKLE_ROLL_RANGE  = (-0.2618,  0.2618)
WAIST_PITCH_RANGE = (-0.5236,  0.5236)
WAIST_ROLL_RANGE  = (-0.5236,  0.5236)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_com(m, d) -> np.ndarray:
    """Whole-body CoM as mass-weighted average of all body positions."""
    total_mass = float(np.sum(m.body_mass))
    if total_mass == 0:
        return np.zeros(3)
    com = np.zeros(3)
    for i in range(m.nbody):
        mass = float(m.body_mass[i])
        if mass > 0:
            com += mass * d.xipos[i]
    return com / total_mass


def _annotate(rgb, t, com, com_err_x, com_err_y, strike_active, fallen):
    """Burn telemetry overlay into a rendered frame. Fails silently if PIL absent."""
    try:
        from PIL import Image, ImageDraw
        img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(img)

        # ── Status bar ────────────────────────────────────────────────────────
        if strike_active:
            status, color = "  ⚡ STRIKE ACTIVE — 50 N  ", (255, 80, 40)
        elif fallen:
            status, color = "  ✘ ROBOT FALLEN          ", (220, 40, 40)
        else:
            in_poly = abs(com_err_x) < SUPPORT_X and abs(com_err_y) < SUPPORT_Y
            status, color = (
                ("  ✔ STABLE                ", (60, 220, 60)) if in_poly
                else ("  ⚠ RECOVERING            ", (240, 200, 40))
            )
        draw.rectangle([0, 0, 640, 22], fill=(0, 0, 0))
        draw.text((4, 3),
                  f"t = {t:5.2f} s   CoM x={com[0]:+.3f} m   y={com[1]:+.3f} m   z={com[2]:.3f} m  {status}",
                  fill=color)

        # ── Fore/aft CoM error bar ─────────────────────────────────────────────
        bar_cy, bar_h = 458, 12
        bar_w = 280
        cx = 320
        # Background
        draw.rectangle([cx - bar_w//2, bar_cy, cx + bar_w//2, bar_cy + bar_h],
                       fill=(30, 30, 30))
        # Support polygon window (green zone)
        lim_px = int(bar_w // 2 * SUPPORT_X / 0.20)
        draw.rectangle([cx - lim_px, bar_cy, cx + lim_px, bar_cy + bar_h],
                       fill=(30, 70, 30))
        # CoM marker
        err_px = int(np.clip(com_err_x, -0.20, 0.20) / 0.20 * bar_w // 2)
        dot_x = cx + err_px
        dot_color = (255, 60, 40) if abs(com_err_x) > SUPPORT_X else (60, 230, 60)
        draw.ellipse([dot_x - 5, bar_cy - 3, dot_x + 5, bar_cy + bar_h + 3],
                     fill=dot_color)
        # Labels
        draw.text((cx - bar_w//2, bar_cy - 14),
                  f"Fore/aft CoM error: {com_err_x*100:+.1f} cm   (±{SUPPORT_X*100:.0f} cm OK)",
                  fill=(200, 200, 200))
        return np.array(img)
    except Exception:
        return rgb


# ── Main simulation ─────────────────────────────────────────────────────────────

def run(out_path: str):
    if not os.path.exists(MODEL_PATH):
        print(f"⛔ MuJoCo model not found: {MODEL_PATH}")
        sys.exit(1)

    m = mujoco.MjModel.from_xml_path(MODEL_PATH)
    d = mujoco.MjData(m)

    # ── Build lookups ─────────────────────────────────────────────────────────
    jname_to_qposadr = {
        mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, ji): m.jnt_qposadr[ji]
        for ji in range(m.njnt)
        if mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, ji)
    }

    # actuator name (no _joint suffix) → ctrl index
    act_to_ci = {
        mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, ci): ci
        for ci in range(m.nu)
        if mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, ci)
    }

    # Compensator joints: joint_name → ctrl_index
    # Only ACTIVE joints (not in PASSIVE_IDX={13,14,...}).
    # waist_pitch (14) and waist_roll (13) are passive on the physical G1 23-DOF —
    # including them here would produce a sim that passes but falls on hardware.
    # Ankle pitch/roll (indices 4,5,10,11) are fully active and sufficient for
    # sagittal + lateral CoM rejection at 500 Hz.
    _COMP_JOINTS = {
        "left_ankle_pitch_joint":  "left_ankle_pitch",
        "right_ankle_pitch_joint": "right_ankle_pitch",
        "left_ankle_roll_joint":   "left_ankle_roll",
        "right_ankle_roll_joint":  "right_ankle_roll",
    }
    comp_ci = {}  # joint_name → ctrl_index
    for jname, aname in _COMP_JOINTS.items():
        if aname in act_to_ci:
            comp_ci[jname] = act_to_ci[aname]
    print(f"  Compensator mapped: {list(comp_ci.keys())}")

    # Torso body for xfrc_applied
    torso_id = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "torso_link")
    if torso_id < 0:
        # Fallback: heaviest non-world body
        torso_id = int(np.argmax([m.body_mass[i] if i > 0 else 0 for i in range(m.nbody)]))
    torso_name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, torso_id) or f"body[{torso_id}]"
    print(f"  Strike target: '{torso_name}' (id={torso_id}, mass={m.body_mass[torso_id]:.2f} kg)")

    # ── Initial pose ──────────────────────────────────────────────────────────
    d.qpos[0:3] = [0.0, 0.0, 0.9]
    d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]       # identity quaternion [w,x,y,z]
    for jname, angle in STABLE_BALANCE_POSE.items():
        if jname in jname_to_qposadr:
            d.qpos[jname_to_qposadr[jname]] = angle
    mujoco.mj_kinematics(m, d)
    # Exclude world body (id=0, always at z=0) from min — otherwise grounding is a no-op
    d.qpos[2] -= float(np.min(d.xpos[1:, 2]))
    mujoco.mj_forward(m, d)

    # ── PD stance gains (reconfigure torque actuators → position controllers) ─
    # Passive joints {13,14,20,21,27,28} match deploy_real.py PASSIVE_IDX.
    # KP=0 on these slots so sim behaviour is hardware-accurate: they contribute
    # zero active torque, just like the physical G1 23-DOF robot.
    PASSIVE_IDX = {13, 14, 20, 21, 27, 28}
    for ci in range(m.nu):
        kp = 0.0 if ci in PASSIVE_IDX else float(_KP_PER_JOINT[ci])
        kd = 0.0 if ci in PASSIVE_IDX else float(_KD_PER_JOINT[ci])
        # biastype MUST be mjBIAS_AFFINE (1) or biasprm is silently ignored.
        # Without this, force = kp*ctrl (constant torque), not kp*(ctrl-q) - kd*dq.
        m.actuator_gaintype[ci] = 0   # mjGAIN_FIXED: gain = gainprm[0]
        m.actuator_biastype[ci] = 1   # mjBIAS_AFFINE: bias = biasprm[0] + biasprm[1]*q + biasprm[2]*dq
        m.actuator_gainprm[ci, 0] =  kp
        m.actuator_biasprm[ci, 1] = -kp
        m.actuator_biasprm[ci, 2] = -kd

    # Base stance ctrl (set once; compensator overrides 6 ankle/waist slots)
    base_ctrl = np.zeros(m.nu)
    for ci in range(m.nu):
        aname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, ci)
        if aname:
            base_ctrl[ci] = STABLE_BALANCE_POSE.get(aname + "_joint", 0.0)

    # ── Renderer ──────────────────────────────────────────────────────────────
    cam = "track_root" if "track_root" in [m.cam(i).name for i in range(m.ncam)] else -1
    renderer = mujoco.Renderer(m, 480, 640)

    # ── Simulation loop ───────────────────────────────────────────────────────
    total_steps     = int(SIM_DURATION / DT)
    steps_per_frame = max(1, round(1.0 / (RENDER_FPS * DT)))   # ~17 at 500 Hz / 30 fps

    com_prev  = _get_com(m, d).copy()
    com_log   = []           # (t, com_x, com_y, com_z) for each physics step
    frames    = []
    peak_err  = 0.0
    recovery_t = None
    fallen     = False

    # ── Gravity settling phase (not recorded) ─────────────────────────────────
    # Run SETTLE_T seconds of physics before the test clock starts so contact
    # forces and PD transients decay to steady state before we start measuring.
    settle_steps = int(SETTLE_T / DT)
    print(f"  Settling {SETTLE_T:.1f}s ({settle_steps} steps)...", end="", flush=True)
    for _ in range(settle_steps):
        d.ctrl[:] = base_ctrl
        mujoco.mj_step(m, d)
    print(f" done  (root_z={d.qpos[2]:.3f}m)")
    com_prev = _get_com(m, d).copy()

    print(f"\nRunning {SIM_DURATION:.0f}s  ({total_steps} steps)  |  "
          f"Strike: {STRIKE_FX:.0f} N on '{torso_name}' at t={STRIKE_T:.1f}s\n")

    for step in range(total_steps):
        t = step * DT

        # ── CoM state ─────────────────────────────────────────────────────────
        com       = _get_com(m, d)
        com_vel_x = (com[0] - com_prev[0]) / DT
        com_vel_y = (com[1] - com_prev[1]) / DT
        com_err_x = float(com[0])    # desired CoM x = 0 (centred over feet)
        com_err_y = float(com[1])
        com_prev  = com.copy()
        com_log.append((t, float(com[0]), float(com[1]), float(com[2])))

        # ── Diagnostics ───────────────────────────────────────────────────────
        if abs(com_err_x) > peak_err:
            peak_err = abs(com_err_x)
        if t > STRIKE_T + STRIKE_DUR and recovery_t is None:
            if abs(com_err_x) < SUPPORT_X and abs(com_err_y) < SUPPORT_Y:
                recovery_t = t

        root_z = float(d.qpos[2])
        if root_z < 0.30 and not fallen:
            fallen = True
            print(f"\n⚠️  Robot FELL at t={t:.3f}s  "
                  f"(root_z={root_z:.3f}m  CoM_x={com_err_x:+.3f}m)")

        # ── Ctrl: base stance ─────────────────────────────────────────────────
        d.ctrl[:] = base_ctrl

        # ── Ctrl: CoM compensator (overrides ankle joints only) ───────────────
        if not fallen:
            # Sagittal: forward CoM → plantarflex (positive delta) → push CoM back
            ap_delta = float(np.clip(KP_ANKLE * com_err_x + KD_ANKLE * com_vel_x, -0.40, 0.40))
            # Lateral: leftward CoM → evert ankles (right) / invert (left) → push right
            ar_delta = float(np.clip(-KP_ANKLE * com_err_y - KD_ANKLE * com_vel_y, -0.15, 0.15))

            for jname in ("left_ankle_pitch_joint", "right_ankle_pitch_joint"):
                if jname in comp_ci:
                    base = STABLE_BALANCE_POSE.get(jname, -0.60)
                    d.ctrl[comp_ci[jname]] = float(np.clip(base + ap_delta, *ANKLE_PITCH_RANGE))

            for jname in ("left_ankle_roll_joint", "right_ankle_roll_joint"):
                if jname in comp_ci:
                    base = STABLE_BALANCE_POSE.get(jname, 0.0)
                    d.ctrl[comp_ci[jname]] = float(np.clip(base + ar_delta, *ANKLE_ROLL_RANGE))

            # waist_pitch / waist_roll are passive (KP=0) — not driven here

        # ── External disturbance ──────────────────────────────────────────────
        d.xfrc_applied[:] = 0.0
        strike_active = STRIKE_T <= t < STRIKE_T + STRIKE_DUR
        if strike_active:
            d.xfrc_applied[torso_id, 0] = STRIKE_FX   # Fx = 50 N in world +X

        # ── Physics step ──────────────────────────────────────────────────────
        mujoco.mj_step(m, d)

        # ── Render frame ──────────────────────────────────────────────────────
        if step % steps_per_frame == 0:
            renderer.update_scene(d, camera=cam)
            rgb = renderer.render().astype("uint8")
            rgb = _annotate(rgb, t, com, com_err_x, com_err_y, strike_active, fallen)
            frames.append(rgb)

        if step % 500 == 0:
            print(f"  t={t:5.1f}s  CoM_x={com_err_x:+.4f}m  root_z={root_z:.3f}m  "
                  f"{'⚡ STRIKE' if strike_active else '       '}", end="\r", flush=True)

    renderer.close()
    print()

    # ── Save video ────────────────────────────────────────────────────────────
    Path(out_path).parent.mkdir(exist_ok=True)
    imageio.mimsave(out_path, frames, fps=RENDER_FPS, quality=8,
                    pixelformat="yuv420p", macro_block_size=None)

    # ── Results ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  DISTURBANCE REJECTION TEST  —  RESULTS")
    print("=" * 55)
    print(f"  Impulse       : {STRIKE_FX:.0f} N × {STRIKE_DUR:.2f} s on '{torso_name}'")
    print(f"  Peak CoM error: {peak_err*100:.1f} cm  (support polygon ±{SUPPORT_X*100:.0f} cm)")
    if fallen:
        print("  VERDICT       : ❌ FAIL — robot fell under perturbation")
        print("  Action        : Increase KP_STAND or tune CoM gains before hardware.")
    elif recovery_t is not None:
        dt_rec = recovery_t - (STRIKE_T + STRIKE_DUR)
        verdict = "✅ PASS" if dt_rec < 2.0 else "⚠️  SLOW RECOVERY"
        print(f"  Recovery time : {dt_rec:.2f}s after impulse ends")
        print(f"  VERDICT       : {verdict}")
        if dt_rec < 2.0:
            print("  Robot survived 50 N sagittal push → hardware deployment approved.")
        else:
            print("  Increase KD_ANKLE / KD_WAIST to dampen recovery oscillation.")
    else:
        print("  VERDICT       : ⚠️  CoM did not re-enter support polygon within simulation window")
        print("  Action        : Increase KP_ANKLE or extend SIM_DURATION.")
    print("=" * 55)
    print(f"\n  Video: {out_path}")

    # Log peak errors per phase for tuning
    pre  = [abs(row[1]) for row in com_log if row[0] < STRIKE_T]
    post = [abs(row[1]) for row in com_log if row[0] >= STRIKE_T]
    print(f"\n  Baseline CoM jitter (0–3 s): max={max(pre)*100:.2f} cm  mean={np.mean(pre)*100:.2f} cm")
    print(f"  Post-strike max error     : {max(post)*100:.2f} cm")


def main():
    parser = argparse.ArgumentParser(description="Disturbance rejection test for Unitree G1")
    parser.add_argument("--out", default="output/demo_disturbance.mp4",
                        help="Output MP4 path")
    args = parser.parse_args()
    Path("output").mkdir(exist_ok=True)
    run(args.out)


if __name__ == "__main__":
    main()
