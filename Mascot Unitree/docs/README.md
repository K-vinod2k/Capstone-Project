# 🦸 HeroPose — Voice-Driven Persona-Based Motion Control for a Humanoid Robot

> **Capstone Project** · Unitree G1 Mascot Robot  
> Voice → LLM Persona Brain → AI Video Generation → MuJoCo Physics Simulation → React Dashboard

---

## 📌 Overview

HeroPose is an end-to-end pipeline that lets you **speak a superhero's name**, automatically detect the persona, and watch a Unitree G1 humanoid robot perform that hero's signature gesture — complete with an AI-generated reference video and a physics-accurate MuJoCo simulation rendered in real time.

```
Voice Input
    │
    ▼
Persona Detection (persona_brain.py)
    │  GPT-4o classifies hero + generates iconic spoken reply
    ▼
Gesture Description (LLM prompt)
    │
    ▼
AI Video Generation (Colab / Wan2.1-T2V-1.3B via Ngrok)
    │  Falls back to offline playbook if Colab is unavailable
    ▼
MuJoCo Physics Simulation (server.py → sim_output.mp4)
    │
    ▼
React Dashboard (UI/) — side-by-side: AI video | Robot sim | Hero info
```

---

## 🦸 Supported Personas

| Hero | Icon | Trigger Keywords |
|---|---|---|
| Spider-Man | 🕸️ | spider, spidey, peter, web … |
| Iron Man | 🚀 | iron, stark, tony, jarvis … |
| Hulk | 💚 | hulk, smash, bruce, gamma … |
| Captain America | 🛡️ | captain, cap, rogers, shield … |
| Thor | ⚡ | thor, mjolnir, asgard, thunder … |
| Black Widow | 🕵️ | widow, natasha, romanoff … |
| Batman | 🦇 | batman, bruce, gotham, dark knight … |
| Superman | 🦸 | superman, clark, krypton … |
| Generic Hero | 🤖 | *(any unrecognised input)* |

---

## 🗂️ Project Structure

```
Mascot Unitree/
├── server.py               # FastAPI backend — orchestrates the full pipeline
├── persona_brain.py        # GPT-4o persona engine + hero registry
├── hero_pose.py            # Named joint dictionaries for each persona pose
├── video_client.py         # HTTP client → Colab Wan2.1 video server
├── voice_listener.py       # Microphone → Whisper STT
├── mouth.py                # Text-to-speech output
├── ik_solver.py            # Inverse kinematics for arm trajectories
├── integrated_hero.py      # High-level orchestration helper
├── hero_sim.py             # MuJoCo simulation runner
├── build_cache.py          # Pre-renders offline video playbook
├── offline_playbook/       # Pre-rendered fallback videos + trajectories
│   └── index.json
├── unitree_mujoco/         # Unitree G1 MJCF robot model (submodule)
├── Colab_Video_to_Robot_Server.ipynb  # Colab notebook: Wan2.1 server
└── UI/                     # React + Vite frontend dashboard
    ├── src/
    ├── server.ts           # Bun/Node local API proxy
    ├── vite.config.ts
    └── .env.example        # ← copy to .env and fill in keys
```

---

## ⚙️ Setup

### Prerequisites

| Tool | Version |
|---|---|
| Python | ≥ 3.10 |
| uv | latest (`pip install uv`) |
| Node.js | ≥ 18 |
| MuJoCo | ≥ 3.x (`pip install mujoco`) |
| OpenAI account | API key required |

### 1 · Clone the repo

```bash
git clone https://github.com/<your-org>/mascot-unitree.git
cd "mascot-unitree/Mascot Unitree"
```

### 2 · Python environment

```bash
uv venv capstone_env
source capstone_env/bin/activate
uv pip install -r requirements.txt   # or: uv pip install fastapi uvicorn openai mujoco imageio python-dotenv
```

### 3 · Environment variables

```bash
cp .env.example .env
# Edit .env and fill in your keys:
#   OPENAI_API_KEY=sk-proj-...
#   NGROK_URL=https://your-tunnel.ngrok-free.app
```

> ⚠️ **Never commit `.env`** — it is in `.gitignore`.

### 4 · Frontend

```bash
cd UI
npm install
cp .env.example .env   # if needed
```

---

## 🚀 Running the Pipeline

### Backend (FastAPI)

```bash
# From "Mascot Unitree/"
source capstone_env/bin/activate
python server.py
# → API live at http://localhost:8080/api
```

### Frontend (React / Vite)

```bash
cd UI
npm run dev
# → http://localhost:3000
```

### Colab Video Server (optional — for live AI video)

Open `Colab_Video_to_Robot_Server.ipynb` in Google Colab, run all cells, and copy the Ngrok URL into your `.env` as `NGROK_URL`.  
Without Colab, the system automatically uses the **offline playbook**.

### Building the Offline Playbook (optional)

```bash
python build_cache.py
# Pre-renders one video + trajectory per persona for offline demos
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/run_pipeline` | Run full voice → video pipeline |
| `POST` | `/api/set_ngrok` | Update Colab Ngrok URL at runtime |

**`POST /api/run_pipeline`** body:
```json
{
  "user_prompt": "Hey Spider-Man, save me!",
  "selected_persona": ""
}
```

**Response:**
```json
{
  "spoken_reply": "With great power comes great responsibility.",
  "gesture_description": "A humanoid robot standing upright performs: ...",
  "detected_persona": "Spider-Man",
  "hero_icon": "🕸️",
  "reference_video_b64": "data:video/mp4;base64,...",
  "simulation_video_b64": "data:video/mp4;base64,..."
}
```

---

## 🔐 Security

- API keys are **loaded from `.env`** via `python-dotenv` — never hardcoded.
- `.env` is listed in `.gitignore` at both the root and `UI/` directory levels.
- `.env.example` provides a safe placeholder template for new contributors.
- `CORS` is open (`*`) for local development; restrict in production.

---

## 🤝 Contributing

1. Fork → branch → PR.
2. Copy `.env.example` → `.env` before running locally.
3. Do **not** commit secret files, `*.mp4`, or `capstone_env/`.

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
