"""
viz_architecture.py — Architecture diagram for Mascot Unitree (T1 pipeline).
Run: python viz_architecture.py  →  docs/architecture.png
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

Path("docs").mkdir(exist_ok=True)

BG      = "#0d0d14"
PANEL   = "#13131f"
RED     = "#e94560"
BLUE    = "#1a6fa8"
PURPLE  = "#7c3aed"
TEAL    = "#0e7490"
GREEN   = "#15803d"
GOLD    = "#f6c90e"
TEXT    = "#e2e8f0"
DIM     = "#64748b"
WHITE   = "#f1f5f9"

fig, ax = plt.subplots(figsize=(13, 17))
ax.set_xlim(0, 13); ax.set_ylim(0, 17)
ax.axis("off")
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)


def rbox(x, y, w, h, title, sub="", fc=PANEL, ec=DIM, tsz=10, ssz=8):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.25",
        facecolor=fc, edgecolor=ec, linewidth=1.8, zorder=3))
    ty = y + h/2 + (0.17 if sub else 0)
    ax.text(x + w/2, ty, title, ha="center", va="center",
            color=WHITE, fontsize=tsz, fontweight="bold", zorder=4)
    if sub:
        ax.text(x + w/2, y + h/2 - 0.2, sub, ha="center", va="center",
                color=DIM, fontsize=ssz, zorder=4)

def arr(x1, y1, x2, y2, color=WHITE, lw=1.6, label="", lcolor=GOLD):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color,
                        lw=lw, mutation_scale=14), zorder=5)
    if label:
        mx, my = (x1+x2)/2 + 0.12, (y1+y2)/2
        ax.text(mx, my, label, color=lcolor, fontsize=7.5,
                va="center", style="italic", zorder=6)

def tag(x, y, text):
    ax.text(x, y, text, color=GOLD, fontsize=7.5, fontweight="bold",
            va="center", zorder=6,
            bbox=dict(boxstyle="round,pad=0.25", fc="#1a1500",
                      ec=GOLD, linewidth=0.8))

def hline(y, x0=0.5, x1=12.5):
    ax.plot([x0, x1], [y, y], color="#1e293b", lw=0.8, zorder=1)


# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(6.5, 16.55, "Mascot Unitree", ha="center", color=WHITE,
        fontsize=18, fontweight="bold")
ax.text(6.5, 16.1, "Voice / Text  ›  Persona  ›  AI Video  ›  Video2Robot  ›  MuJoCo",
        ha="center", color=DIM, fontsize=9)

hline(15.85)

# ── Entry ─────────────────────────────────────────────────────────────────────
tag(0.4, 15.55, "ENTRY")
rbox(0.5, 14.95, 5.2, 0.9, "run_pipeline.py",
     "CLI · voice / text · Whisper · macOS TTS", fc="#1a0d2e", ec=RED)
rbox(7.1, 14.95, 5.2, 0.9, "server.py",
     "FastAPI · CORS · React UI bridge", fc="#1a0d2e", ec=RED)

arr(3.1,  14.95, 6.0, 14.15)
arr(9.7,  14.95, 7.0, 14.15)

hline(14.7)

# ── Persona ───────────────────────────────────────────────────────────────────
tag(0.4, 14.4, "① PERSONA")
rbox(0.8, 13.6, 11.4, 0.95,
     "persona_brain.py  —  Hero Detection + Dialogue",
     "Keyword match → Qwen/Qwen2.5-72B (HuggingFace Inference API)  →  spoken_reply · gesture_description · hero_icon",
     fc="#0f1a2e", ec=BLUE)
arr(6.5, 13.6, 6.5, 13.0, label="gesture_description")

hline(13.45)

# ── Physics gate ──────────────────────────────────────────────────────────────
tag(0.4, 12.75, "② PHYSICS GATE")
rbox(0.8, 12.1, 11.4, 0.85,
     "pipeline.verify_stability(gesture)",
     "Keyword filter (jumping / flying / airborne)  +  NVIDIA Cosmos-Reason2 API if NVIDIA_API_KEY set  →  hard stop on unstable poses",
     fc="#1a0a0a", ec=RED)

# pass arrow
arr(6.5, 12.1, 6.5, 11.5, label="is_stable ✓")
# fail note
ax.text(9.8, 11.78, "✗  returns early", color=RED, fontsize=7.5, va="center")

hline(11.95)

# ── Video gen ─────────────────────────────────────────────────────────────────
tag(0.4, 11.25, "③ VIDEO GEN")
rbox(0.8, 10.45, 11.4, 0.85,
     "pipeline.generate_video()  —  LTX-Video 2.3",
     "Colab Pro (COLAB_URL, free)  ›  fal.ai REST fallback ($0.36 / video)  →  6-second 720p MP4",
     fc="#0a1a1f", ec=TEAL)
arr(6.5, 10.45, 6.5, 9.85, label="ref_video_b64")

hline(10.3)

# ── Motion: T1 ────────────────────────────────────────────────────────────────
tag(0.4, 9.6, "④ MOTION  ·  Tier 1 only")

# V2R sub-stages
rbox(0.8, 8.15, 3.5, 1.1, "PromptHMR",
     "Human pose extraction\nfrom generated video", fc="#150d2b", ec=PURPLE, ssz=7.5)
rbox(4.85, 8.15, 3.5, 1.1, "GMR",
     "SMPL-X → Unitree G1\nmotion retargeting", fc="#150d2b", ec=PURPLE, ssz=7.5)
rbox(8.9, 8.15, 3.3, 1.1, "robot_motion.pkl",
     "dof_pos · root_pos\nroot_rot · fps", fc="#0d1a10", ec=GREEN, ssz=7.5)

# internal flow
arr(6.5, 9.85, 3.15, 9.25, label="video bytes")   # video → PromptHMR
arr(4.3, 8.7, 4.85, 8.7)                            # PromptHMR → GMR
arr(8.35, 8.7, 8.9, 8.7)                            # GMR → pkl

# env labels
ax.text(2.55, 7.95, "conda: phmr  (Python 3.11)", color=DIM, fontsize=7,
        ha="center", style="italic")
ax.text(6.6,  7.95, "conda: gmr  (Python 3.10)", color=DIM, fontsize=7,
        ha="center", style="italic")

arr(10.05, 8.15, 7.8, 7.35, label="trajectory dict")

hline(8.0)

# ── Render ────────────────────────────────────────────────────────────────────
tag(0.4, 7.1, "⑤ RENDER")
rbox(0.8, 6.3, 11.4, 0.85,
     "pipeline.render_mujoco_trajectory()  —  MuJoCo",
     "Kinematic mode (no physics stepping)  ·  legs locked to STABLE_BALANCE_POSE  ·  480 × 640 @ 30 fps",
     fc="#0a1f1a", ec=GREEN)
arr(6.5, 6.3, 6.5, 5.7)

hline(6.15)

# ── Output ────────────────────────────────────────────────────────────────────
tag(0.4, 5.45, "OUTPUT")
rbox(0.8,  4.65, 4.9, 0.85, "output/ref_<ts>.mp4",
     "AI reference video (LTX)", fc="#0a1a1f", ec=TEAL)
rbox(7.3,  4.65, 4.9, 0.85, "output/sim_<ts>.mp4",
     "Robot simulation video", fc="#0a1a1f", ec=TEAL)
arr(5.7, 5.08, 7.3, 5.08, label="paired", lcolor=DIM)

hline(4.5)

# ── File map ──────────────────────────────────────────────────────────────────
ax.add_patch(FancyBboxPatch((0.3, 0.2), 12.4, 3.9,
    boxstyle="round,pad=0,rounding_size=0.25",
    facecolor="#0d1117", edgecolor="#1e293b", linewidth=1, zorder=2))

ax.text(6.5, 3.87, "Source Files", ha="center", color=GOLD,
        fontsize=9, fontweight="bold", zorder=4)

rows = [
    ("run_pipeline.py",  GOLD,   "CLI entrypoint · Ear (Whisper) · speak() · T1-only motion path"),
    ("server.py",        GOLD,   "FastAPI wrapper · CORS · PipelineRequest / PipelineResponse"),
    ("pipeline.py",      "#22d3ee", "generate_video() · verify_stability() · render_mujoco_trajectory() · run_video2robot_pipeline()"),
    ("persona_brain.py", "#22d3ee", "HERO_REGISTRY · Qwen2.5-72B chat completion · mock fallback"),
    ("hero_pose.py",     "#22d3ee", "STABLE_BALANCE_POSE · named pose dicts · animate() interpolation"),
    ("kinematic_brain.py", "#64748b", "URDF limits · ZMP/CoM check (not in T1 path — available if needed)"),
]
for i, (fname, fc, desc) in enumerate(rows):
    y = 3.32 - i * 0.52
    ax.text(0.65, y, fname, color=fc, fontsize=8.5, fontweight="bold",
            va="center", zorder=4)
    ax.text(4.1,  y, desc, color=DIM if fc == "#64748b" else "#94a3b8",
            fontsize=7.8, va="center", zorder=4, style="italic" if fc == "#64748b" else "normal")

plt.tight_layout(pad=0)
out = "docs/architecture.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close()
print(f"Saved → {out}")
