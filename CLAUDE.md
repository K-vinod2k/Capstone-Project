# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Unitree G1 Capstone: voice/text → superhero persona → AI video → human pose extraction → robot joint angles → (optional) real hardware. Two machines collaborate: **Vinod's Mac** runs the video/motion/persona pipeline; **Kim's GPU Linux machine** runs Isaac Lab RL training and hardware DDS control.

```
vinod_workspace/   — Mac-side: persona, video→motion pipeline, physics eval, hardware deploy
kim_workspace/     — Linux GPU: Isaac Lab RL training, hardware deployment utilities, movement PKLs
main.py            — Root CLI entry point (text or voice → persona → PKL replay)
example.py         — Standalone interactive demo (RAG → hero reply → animation)
```

---

## vinod_workspace (Mac Pipeline)

**End-to-end flow:** `main.py` → `persona_brain.py` (Qwen2.5-72B) → gesture description → `video2robot/` pipeline (Veo/Sora → PromptHMR → GMR) → PKL → `mujoco_physics_eval.py` → (if safe) `deploy_real.py`

### Commands

```bash
# Root CLI — primary entry point
python main.py --text "Hey Spider-Man!"   # text mode
python main.py                            # voice mode (requires microphone + sounddevice)

# Standalone interactive demo
python example.py
ROBOT_INTERFACE=eth0 python example.py   # real hardware

# Progressive hardware safety test (run before deploy_real.py on new hardware)
python kim_workspace/hardware_deployment/safe_experiment.py --interface eth0

# Full deployment to real robot
python vinod_workspace/deploy_real.py --pkl kim_workspace/movements/wave_kinematics.pkl \
    --iface enp0s31f6 --speed 0.5
# enp0s31f6 is the confirmed interface on iotlab Linux; --peer not required on Linux

# Arm-only replay (gantry/suspended robot)
python kim_workspace/hardware_deployment/g1_arm_replay_airborne.py \
    --pkl kim_workspace/movements/wave_kinematics.pkl --both-arms

# VLAW recovery sync server (FastAPI on port 8080)
python vinod_workspace/server.py

# Physics validation
python vinod_workspace/mujoco_physics_eval.py

# Render hero animation to MP4
python vinod_workspace/render_animations.py --animation hulk_smash

# RAG dataset + retrieval
python vinod_workspace/generate_rag_dataset.py
python vinod_workspace/rag_retrieve.py

# Inspect a PKL file (shape, joint ranges, velocity stats)
python vinod_workspace/inspect_pkl.py kim_workspace/movements/hulk_smash_kinematics.pkl

# Clamp PKL velocities to ≤ 2.0 rad/s (run before hardware deploy on new PKLs)
python vinod_workspace/clamp_pkls.py
```

### Environment Setup

Create `.env` in `vinod_workspace/` with:
- `HF_TOKEN` — HuggingFace token for Qwen2.5-72B in `persona_brain.py` (falls back to mock mode without it)
- `ANTHROPIC_API_KEY` — Claude API (used if LLM-grounded kinematics path is active)
- `GOOGLE_API_KEY` — Google Veo video generation
- `OPENAI_API_KEY` — OpenAI Sora (fallback video gen)

### Key Modules

- `persona_brain.py` — Qwen2.5-72B persona engine; HERO_REGISTRY maps keywords → 9 Marvel/DC characters; returns `spoken_reply`, `gesture_description`, `internal_reasoning` (SCoT); falls back to mock mode without `HF_TOKEN`
- `hero_pose.py` — Static joint angle dicts + 10 named hero animation sequences; offline fallback, always available
- `mujoco_physics_eval.py` — Runs PD-control sim in MuJoCo to verify poses before hardware; checks ZMP/CoM
- `deploy_real.py` — 500 Hz PD control via unitree_sdk2py; reads encoder state → 3-second ease-in → plays PKL trajectory; dual-tier gains: Kp=200 legs/waist, Kp=60 arms; hard-kills all torque if any joint exceeds 10 rad/s
- `render_animations.py` — Headless MuJoCo → MP4 for sim preview
- `server.py` — Minimal FastAPI endpoint (`/vlaw_sim_sync`) that receives crash telemetry from Isaac Lab and returns recovery PKL path
- `rag_retrieve.py` — FAISS semantic search (sentence-transformers all-MiniLM-L6-v2) to match user intent to nearest hero gesture PKL
- `clamp_pkls.py` — Clamps all PKLs in `kim_workspace/movements/` to ≤ 2.0 rad/s inter-frame velocity; run before hardware deploy on new PKLs

**G1 EDU Two-Computer Architecture:**
- `192.168.123.161` — Locomotion computer (black box, runs Unitree's balance/locomotion controller, no SSH access)
- `192.168.123.164` — Development computer (Jetson Orin NX, SSH: `unitree/123`, your code runs here)
- High-level balance + low-level arm control simultaneously **IS officially supported** via the `rt/arm_sdk` DDS topic with the weight bit at `motor_cmd[29].q` (Unitree issue [#108](https://github.com/unitreerobotics/unitree_sdk2_python/issues/108); upstream reference `g1_arm7_sdk_dds_example.py`). **Two deployment paths now exist:**
  - (a) **`deploy_real.py`** — calls `MotionSwitcherClient.ReleaseMode()` and takes full 23-DOF low-level control of legs + arms. Robot cannot walk or self-balance while this runs. Use for full-body hero poses on a gantry.
  - (b) **`vinod_workspace/g1_arm_replay_loco.py`** — publishes arm-only commands on `rt/arm_sdk` while the locomotion controller keeps legs and waist balanced. Weight bit blends arm-SDK authority with `BalanceStand()`. Robot can walk while the arm gesture plays. This is the default for arm-only replay. See `kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md` for the four-gate pre-flight procedure.
- To exit debug mode: **reboot required** (L2+R2 → L2+A → L2+B enters debug mode; only exit is reboot).

**Real robot prereqs:** Ubuntu + Ethernet to G1 at `192.168.123.x`; robot in DAMPING mode (L2+B on controller); keep L1+L2 e-stop ready.

**Confirmed hardware deployment sequence (validated 2026-04-13):**
1. Robot in DAMPING mode (L2+B), gantry attached
2. Run `g1_encoder_monitor.py` — confirm joint 13 = L_shoulder_pitch
3. Run `safe_experiment.py --interface eth0` (phases 0→1→2)
4. Run `deploy_real.py --pkl ... --iface enp0s31f6 --speed 0.5`

**DDS notes:**
- Linux direct Ethernet: CycloneDDS multicast works, `--peer` not required
- macOS: requires explicit `--peer 192.168.123.164`
- `mode_machine` must be read from the first `LowState` and echoed in every `LowCmd` — hardcoding 0 causes silent discard
- CRC must be recomputed before every `publisher.Write(cmd)` call — missing CRC causes silent discard

**Safety constants in `deploy_real.py`:**
- `VELOCITY_ABORT_THRESHOLD = 10.0` rad/s — instant torque kill
- `CTRL_HZ = 500.0` — control loop frequency
- Ease-in: 3-second linear interpolation from current encoder state to first PKL frame

---

## vinod_workspace/video2robot (Motion Pipeline)

**Pipeline:** Text/Video → Veo/Sora (video gen) → PromptHMR (human pose, Python 3.11 `phmr` conda) → SMPL-X → GMR (retargeting, Python 3.10 `gmr` conda) → PKL

```bash
cd vinod_workspace/video2robot
pip install -e .   # installs `video2robot` CLI

# Full pipeline
python scripts/run_pipeline.py --action "wave hello"

# Individual steps
python scripts/generate_video.py
python scripts/extract_pose.py
python scripts/convert_to_robot.py
python scripts/visualize.py

# Web UI (FastAPI + Jinja2 + Viser 3D, port 8000)
uvicorn web.app:app --host 0.0.0.0 --port 8000

# Linting
ruff check .
black .
```

Scripts auto-switch conda environments via subprocess (`run_in_conda()`). `third_party/` contains PromptHMR and GMR as git submodules (non-commercial research license).

**Linting:** ruff + black, line-length 100, configured in `pyproject.toml`.

---

## kim_workspace (GPU Linux Machine)

### RL Training (Isaac Lab)

Trains a PPO policy to track video-generated pose targets without falling. Requires Linux + NVIDIA GPU + Isaac Lab installed.

```bash
# From inside Isaac Lab Python environment
./isaaclab.sh -p kim_run/train.py --headless --num_envs 4096
```

Key files in `kim_workspace/rl_training/`:
- `train.py` — Entry point; launches 4096 Isaac Lab env clones
- `g1_rewards.py` — Pose-tracking reward (exponential kernel) + fall penalty (−100 if root Z < 0.4 m) + imitation recovery reward
- `g1_randomization.py` — Domain randomization (mass, friction) for sim-to-real robustness
- `sim_logger.py` — Monitors simulation state; on ZMP collapse or height < 0.4 m, POSTs to `vinod_workspace/server.py /vlaw_sim_sync` to trigger recovery animation
- `vlaw_orchestrator.py` — Orchestrates Isaac Lab episode lifecycle + crash → recovery loop

### Hardware Deployment

Key files in `kim_workspace/hardware_deployment/`:
- `g1_arm_replay_airborne.py` — Arm-only kinematic playback via DDS; 200 Hz, Kp=20 (loose, ~10% of sim). Default: left arm only; pass `--both-arms` to command both.
- `safe_experiment.py` — 3-phase progressive safety test (DDS readback → single joint wiggle → wave animation); run before any full deployment on new hardware
- `g1_encoder_monitor.py` — Reads real G1 joint encoders via DDS
- `check_dds_connection.py` — DDS network diagnostics
- `unitree_mujoco/` — Complete Unitree MuJoCo simulator (C++ + Python bindings); contains `unitree_robots/g1/` with URDF/MJCF assets

### Movement PKLs

Pre-recorded hero animation trajectories live in `kim_workspace/movements/`:
```
captain_america_shield_kinematics.pkl
hulk_smash_kinematics.pkl
iron_man_repulsor_kinematics.pkl
spider_man_web_shoot_kinematics.pkl
thor_lightning_kinematics.pkl
wave_kinematics.pkl   # + others
```

---

## Joint Map — 23-DOF Hardware IDL

All PKL files and hardware deployment scripts use the G1 23-DOF IDL layout. `deploy_real.py` and `g1_arm_replay_airborne.py` both expect this scheme. `ARM_JOINTS = range(13, 23)`.

```
 0-11: legs (hip_pitch/roll/yaw, knee, ankle x2, both sides)
12:    waist_yaw (TORSO)
13-17: left arm  (L_shoulder_pitch/roll/yaw, L_elbow_pitch, L_elbow_roll)
18-22: right arm (R_shoulder_pitch/roll/yaw, R_elbow_pitch, R_elbow_roll)
23-34: unused (zero torque only)
```

**R_shoulder_roll sign flip:** Index 19 (R_shoulder_roll) is negated in `deploy_real.py` because the right arm motor is physically mirrored. Applied in both ease-in and playback phases. Under active testing — see `_kpop/` logs.

---

## PKL Format

**PKL dict key:** `joint_angles` — shape `(N, 35)` — 35 columns matching the hardware IDL motor count.

All movement PKLs in `kim_workspace/movements/` have been processed by `clamp_pkls.py` and are clamped to ≤ 2.0 rad/s inter-frame velocity. New PKLs from the video2robot pipeline must be clamped before hardware deployment.

**MuJoCo model** (in `kim_workspace/hardware_deployment/unitree_mujoco/unitree_robots/g1/`):
- `g1_23dof.xml` — G1 23-DOF simulation model (loaded via `scene.xml`)

---

## VLAW Loop (Sim-to-Real Co-Improvement)

When Isaac Lab detects a fall (root Z < 0.4 m), `sim_logger.py` sends telemetry to `vinod_workspace/server.py /vlaw_sim_sync`. The server returns a recovery PKL path; `vlaw_orchestrator.py` feeds this back into RL as imitation learning data. This creates a crash → synthetic recovery → retrain loop.

---

## Known Open Issues

- **Right arm not commanding in `main.py` and `example.py`:** Both `_replay_hardware()` functions import and use only `LEFT_ARM` from `g1_arm_replay_airborne`. Pass `LEFT_ARM + RIGHT_ARM` to `ArmReplayController` to enable both arms.
- **No ease-out phase:** After PKL playback finishes, scripts drop directly to zero torque (limp). A researcher noted this can stress joints. An ease-out (interpolate from last frame back to neutral over ~2s) should be added before zero-torque disengage.
- **Motion dynamics:** All PKLs were clamped to ≤ 2.0 rad/s; `g1_arm_replay_airborne.py` uses Kp=20 (10% of sim Kp) for deliberately loose tracking. If motion feels sluggish, increase Kp or use `deploy_real.py` (Kp=60) instead.
- **R_shoulder_roll sign flip (index 19):** Under active investigation in `_kpop/` logs. Currently applied in `deploy_real.py` but not in `g1_arm_replay_airborne.py`.

---

## Testing

No automated test suite. Validate changes manually:
- `python main.py --text "..."` for end-to-end pipeline smoke test
- `python vinod_workspace/mujoco_physics_eval.py` to verify a pose is stable
- `python kim_workspace/hardware_deployment/safe_experiment.py --interface lo` (sim) before hardware
- Check `_kpop/` for KPOP-style experiment logs documenting past hypotheses and failures
