# HeroPose — Voice-Driven Persona-Based Motion Control for a Humanoid Robot

> **Capstone Project** · Unitree G1 · Voice → LLM → AI Video → Video2Robot → MuJoCo → Real Robot

---

## Overview

HeroPose is an end-to-end pipeline: speak a superhero's name, watch a Unitree G1 humanoid perform that hero's signature gesture — with an AI-generated reference video, physics-accurate MuJoCo simulation, and optional real-robot deployment.

```
Voice / Text Input
    │
    ▼
Persona Engine (persona_brain.py)
    │  Qwen2.5-72B via HuggingFace — classifies hero + generates spoken reply
    ▼
Physics Gate (pipeline.py → verify_stability)
    │  Cosmos-Reason2-2B VLM — checks gesture feasibility with live G1 render
    ▼
AI Video Generation (ltx_video_client.py)
    │  LTX-Video 2.3 via fal.ai or Colab fallback
    ▼
Motion (pipeline.py)
    │  Tier 1: Video2Robot (PromptHMR + GMR) — human pose → G1 joint angles
    │  Tier 2: LLM-grounded kinematics (kinematic_brain.py)
    │  Tier 3: Hero animation library (hero_pose.py)
    ▼
MuJoCo Simulation (simulate.py)
    │  Kinematic or physics+gravity mode, root_pos/rot applied from trajectory
    ▼
React Dashboard (UI/) — reference video | robot sim | hero info
    │
    ▼ (optional)
Real Robot Deployment (deploy_real.py)
    │  500 Hz PD control via unitree_sdk2py → Unitree G1 hardware
```

---

## Supported Personas

| Hero | Icon | Trigger Keywords |
|---|---|---|
| Spider-Man | 🕸️ | spider, spidey, peter, web |
| Iron Man | 🚀 | iron, stark, tony, jarvis |
| Hulk | 💚 | hulk, smash, bruce, gamma |
| Captain America | 🛡️ | captain, cap, rogers, shield |
| Thor | ⚡ | thor, mjolnir, asgard, thunder |
| Black Widow | 🕵️ | widow, natasha, romanoff |
| Batman | 🦇 | batman, bruce, gotham |
| Superman | 🦸 | superman, clark, krypton |
| Generic Hero | 🤖 | *(any unrecognised input)* |

---

## Project Structure

```
Mascot Unitree/
├── server.py               # FastAPI backend (port 8080) — full pipeline
├── run_pipeline.py         # Standalone CLI (text / voice / loop modes)
├── pipeline.py             # Core: video gen, physics gate, MuJoCo render, V2R
├── simulate.py             # Render pkl or video → MP4 (--physics flag)
├── deploy_real.py          # Stream trajectory to real G1 hardware
├── make_demo_pkl.py        # Generate synthetic demo motion pkl
│
├── persona_brain.py        # Qwen2.5-72B persona detection + hero registry
├── kinematic_brain.py      # LLM-grounded joint angle generation (Tier 2)
├── hero_pose.py            # Named joint dicts for each hero (Tier 3 fallback)
│
├── ltx_video_client.py     # LTX-Video 2.3 client (fal.ai / Colab)
├── cogvideo_client.py      # CogVideo alternative
├── hf_video_client.py      # HuggingFace video fallback
├── v2r_integration.py      # Video2Robot pipeline integration
│
├── unitree_mujoco/         # Unitree G1 MJCF models (g1_23dof, g1_29dof)
├── output/                 # Rendered MP4s and pkl motion files (git-ignored)
│
└── UI/                     # React 19 + TypeScript + Vite dashboard
    ├── src/App.tsx
    ├── server/             # Express proxy + better-sqlite3
    └── .env.example
```

---

## Setup

### Environment

```bash
cd "Mascot Unitree"
uv venv capstone_env && source capstone_env/bin/activate
pip install -r requirements.txt   # or: uv pip install ...
cp .env.example .env              # fill in keys
```

Required keys in `.env`:

| Key | Purpose |
|---|---|
| `HF_TOKEN` | HuggingFace — Qwen2.5-72B persona brain |
| `FAL_KEY` | fal.ai — LTX-Video 2.3 generation |
| `NVIDIA_API_KEY` | Cosmos-Reason2 physics gate |
| `COLAB_URL` | Optional Colab fallback for video gen |
| `OPENAI_API_KEY` | Optional fallback LLM |

### Frontend

```bash
cd "Mascot Unitree/UI"
npm install
npm run dev    # React dev server on port 3000
```

---

## Usage

### CLI

```bash
source capstone_env/bin/activate

# Interactive text loop
python run_pipeline.py

# Single prompt
python run_pipeline.py --text "Hey Spider-Man, shoot a web!"

# Skip video generation (fast test)
python run_pipeline.py --text "..." --no-video

# Voice input
python run_pipeline.py --voice
```

### Backend

```bash
python server.py    # FastAPI on port 8080
```

### Simulation only (from pkl)

```bash
# Kinematic (exact pose replay)
python simulate.py --pkl output/2026-03-12_07-07-09.pkl

# Physics + gravity
python simulate.py --pkl output/2026-03-12_07-07-09.pkl --physics

# From video (runs Video2Robot pipeline)
python simulate.py --video output/ref_video.mp4
```

### Generate demo motion

```bash
python make_demo_pkl.py   # → output/spiderman_webshoot.pkl
```

---

## Real Robot Deployment

Requires Ubuntu machine connected to G1 via Ethernet (`192.168.123.x`).

```bash
# Install SDK (Linux only)
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
cd unitree_sdk2_python && pip install -e .

# Validate limits (no robot motion)
python deploy_real.py --pkl output/2026-03-12_07-07-09.pkl --dry-run

# Deploy at half speed (first test)
python deploy_real.py --pkl output/2026-03-12_07-07-09.pkl --iface eth0 --speed 0.5

# Full speed
python deploy_real.py --pkl output/2026-03-12_07-07-09.pkl --iface eth0
```

**Before running:** robot must be in DAMPING mode (L2+A on controller). Keep L1+L2 e-stop ready.

The deploy script: reads current joint state → eases to stand pose (5s) → eases to first pkl frame (3s) → plays trajectory at 500 Hz with velocity limiting and joint clamping → returns to stand.

---

## Motion Pipeline Detail

### Tier 1 — Video2Robot (PromptHMR + GMR)

Requires conda envs `phmr` (Python 3.11) and `gmr` (Python 3.10).

```bash
# Full pipeline
python run_pipeline.py --text "Spider-Man web shoot"

# The pkl stores: dof_pos (N×29), root_pos (N×3), root_rot (N×4 qxyzw), fps
```

### Tier 2 — LLM Kinematics

`kinematic_brain.py` injects G1 URDF joint limits into the LLM prompt and generates ZMP-stable trajectories without video.

### Tier 3 — Hero Pose Library

`hero_pose.py` provides offline named pose dicts for each hero. Always available — used when video APIs and LLM are both unavailable.

---

## MuJoCo Render Engine

`pipeline.py: render_mujoco_trajectory()`

| Mode | Description |
|---|---|
| Kinematics (default) | Joint angles set directly each frame, no gravity |
| Physics (`--physics`) | PD actuators (kp=200, kd=10) + gravity + contact, 150 Hz |

Root pose from pkl is applied each frame:
- **x, y**: trajectory translation
- **z**: trajectory height minus lowest-body offset (auto-grounded to floor)
- **orientation**: trajectory quaternion applied to root body

---

## G1 Joint Map (29 DOF)

```
 0-5:  left leg   (hip_pitch/roll/yaw, knee, ankle_pitch/roll)
 6-11: right leg  (same)
12:    waist_yaw
13-14: waist_roll, waist_pitch  (passive in 23-DOF)
15-21: left arm   (shoulder_pitch/roll/yaw, elbow, wrist_roll/pitch/yaw)
22-28: right arm  (same)
```

---

## Video2Robot Sub-Project

See [`../video2robot/README.md`](../video2robot/README.md) for the standalone V2R pipeline (Veo/Sora → PromptHMR → GMR → pkl).
