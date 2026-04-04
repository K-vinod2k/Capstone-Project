# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered robotics capstone with two active sub-projects exploring humanoid robot control via voice and video. The primary project is **Mascot Unitree (HeroPose)**.

## Sub-Projects

| Project | Purpose | Status |
|---------|---------|--------|
| `Mascot Unitree/` | Voice-driven hero persona control for Unitree G1 robot | Primary/Active |
| `video2robot/` | Modular video-to-robot-motion pipeline | Stable framework |

---

## Mascot Unitree (HeroPose)

**Pipeline:** Voice/Text → Persona Detection (Qwen2.5-72B) → Physics Gate (Cosmos-Reason2) → AI Video Generation → Motion Extraction → MuJoCo Simulation → React Dashboard → (optional) Real Robot

### Commands

```bash
# Backend (FastAPI on port 8080)
cd "Mascot Unitree"
source capstone_env/bin/activate   # or: uv venv capstone_env && source capstone_env/bin/activate
pip install -r requirements.txt
python server.py

# CLI pipeline runner
python run_pipeline.py                          # interactive text loop
python run_pipeline.py --text "Hey Spider-Man!" # single prompt
python run_pipeline.py --text "..." --no-video  # skip video gen (fast test)
python run_pipeline.py --voice                  # microphone input

# Simulation from pkl or video
python simulate.py --pkl output/<file>.pkl       # kinematic (exact pose replay)
python simulate.py --pkl output/<file>.pkl --physics  # physics + gravity (PD actuators)
python simulate.py --video output/ref_video.mp4  # runs Video2Robot pipeline

# Generate demo motion
python make_demo_pkl.py   # → output/spiderman_webshoot.pkl

# Real robot deployment (Linux + Ethernet to G1 only)
python deploy_real.py --pkl output/<file>.pkl --dry-run         # validate limits only
python deploy_real.py --pkl output/<file>.pkl --iface eth0 --speed 0.5  # half speed
python deploy_real.py --pkl output/<file>.pkl --iface eth0              # full speed

# Frontend (React/Vite + Express proxy, port 3000)
cd "Mascot Unitree/UI"
npm install
npm run dev    # starts Express server (tsx server.ts) which proxies to Python backend

# TypeScript type-check (UI)
npm run lint   # runs tsc --noEmit
```

### Environment Setup

Copy `.env.example` to `.env` and set:
- `ANTHROPIC_API_KEY` — Claude API used in `kinematic_brain.py` for LLM-grounded joint angle generation
- `HF_TOKEN` — HuggingFace token for Qwen2.5-72B Inference API used in `persona_brain.py` (falls back to mock mode if missing)
- `NVIDIA_API_KEY` — NVIDIA API for Cosmos-Reason2-2B VLM physics validation in `physics_validator.py`
- `FAL_KEY` — fal.ai for LTX-Video 2.3 generation
- `COLAB_URL` — Colab Pro ngrok URL as fallback for video generation (optional; skips fal.ai when set)

### Architecture

**Motion Generation (three-tier priority):**
1. **Video2Robot extraction** — PromptHMR + GMR for human-to-robot retargeting (`v2r_integration.py`); requires conda envs `phmr` (Python 3.11) and `gmr` (Python 3.10)
2. **LLM-grounded kinematics** — URDF joint limits injected into Claude prompt for ZMP-stable trajectories (`kinematic_brain.py`)
3. **Hero animation library** — Named pose dicts; offline fallback, always available (`hero_pose.py`)

**pkl motion file format:** `dof_pos (N×29 joint angles)`, `root_pos (N×3)`, `root_rot (N×4 qxyzw)`, `fps`

**Key modules:**
- `server.py` — FastAPI orchestrator (port 8080); routes voice/text → persona → video → motion → simulation
- `pipeline.py` — Core orchestration: `verify_stability()` physics gate, `render_mujoco_trajectory()`
- `persona_brain.py` — Qwen2.5-72B (HuggingFace) persona engine; hero registry with trigger keywords; falls back to mock mode without `HF_TOKEN`
- `kinematic_brain.py` — LLM-grounded joint angle generation with URDF constraints and MuJoCo CoM/ZMP validation
- `physics_validator.py` — NVIDIA Cosmos-Reason2 VLM for bipedal stability checks against live G1 render
- `hero_pose.py` — Named joint angle dicts for Spider-Man, Iron Man, Hulk, Captain America, Thor, Black Widow, Batman, Superman
- `ltx_video_client.py` — LTX-Video 2.3 via fal.ai or Colab fallback
- `v2r_integration.py` — Video2Robot pipeline integration
- `UI/server.ts` — Express backend (TypeScript); API proxy to Python FastAPI + better-sqlite3
- `deploy_real.py` — 500 Hz PD control via unitree_sdk2py; reads current joint state → eases to stand → eases to first pkl frame → plays trajectory with velocity limiting and joint clamping

**MuJoCo render modes:**
- Kinematic (default): joint angles set directly each frame, no gravity
- Physics (`--physics`): PD actuators (kp=200, kd=10) + gravity + contact at 150 Hz

**Real robot prereqs:** Ubuntu + Ethernet to G1 at `192.168.123.x`; robot must be in DAMPING mode (L2+A on controller); keep L1+L2 e-stop ready.

**G1 Joint Map (29 DOF):**
```
 0-5:  left leg   (hip_pitch/roll/yaw, knee, ankle_pitch/roll)
 6-11: right leg  (same)
12:    waist_yaw
13-14: waist_roll, waist_pitch  (passive in 23-DOF model)
15-21: left arm   (shoulder_pitch/roll/yaw, elbow, wrist_roll/pitch/yaw)
22-28: right arm  (same)
```

**MuJoCo models:** `unitree_mujoco/g1_23dof.xml`, `g1_29dof.xml`, `g1_29dof_pinned.xml`

**Testing:** No automated test suite. Validate changes via CLI commands above (`--no-video` flag for fast iteration).

---

## video2robot

**Pipeline:** Prompt/Video → AI Video Generation (Veo/Sora) → PromptHMR Pose Extraction → SMPL-X → GMR Motion Retargeting → Robot Motion (pkl)

**Requires two conda environments for GPU pipeline stages (scripts auto-switch via subprocess):**
- `phmr` (Python 3.11) — PromptHMR pose extraction
- `gmr` (Python 3.10) — GMR motion retargeting

### Commands

```bash
cd video2robot
pip install -e .   # installs `video2robot` CLI command

# Full pipeline
python scripts/run_pipeline.py --action "wave hello"

# Individual steps
python scripts/generate_video.py
python scripts/extract_pose.py
python scripts/convert_to_robot.py
python scripts/visualize.py

# Web UI (FastAPI + Jinja2 + Viser 3D visualization, port 8000)
uvicorn web.app:app --host 0.0.0.0 --port 8000

# Linting
ruff check .
black .
```

### Environment Setup

Copy `.env.example` to `.env` and set `GOOGLE_API_KEY` (Veo) and/or `OPENAI_API_KEY` (Sora).

### Architecture

- `video2robot/config.py` — Dataclass configs for all pipeline stages
- `video2robot/video/` — Video generation clients (Veo, Sora, CogVideo) with prompt templates
- `video2robot/pose/` — PromptHMR wrapper for human pose extraction
- `video2robot/robot/` — GMR motion retargeting wrapper
- `web/` — FastAPI + Jinja2 web UI; routers for projects, pipeline, files, and Viser 3D visualization
- `third_party/` — PromptHMR and GMR as git submodules

**Linting:** ruff + black, line-length 100, configured in `pyproject.toml`

**License note:** PromptHMR (in `third_party/`) is non-commercial research only.

**Supported robots:** Unitree G1, H1; Booster T1
