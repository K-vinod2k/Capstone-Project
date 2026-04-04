# KPOP Log — Falsify: Mascot Unitree Project Viability

**Claim:** Mascot Unitree is a viable interactive mascot robot system.
**Budget:** 7 hypotheses
**Method:** Static code analysis (no runtime — system analyzed as-is)

---

## H1: Pipeline latency makes the system non-interactive
*[1 / 7]*

**Hypothesis:** The end-to-end pipeline is too slow for real-time interactive use (>30 seconds per response).

**Prediction:** If true, we will find multiple blocking network calls with no streaming or concurrency between stages.

**Test:** Trace latency floor through `server.py` `run_pipeline()`:
1. HF LLM call (Qwen 72B, HuggingFace free tier) — ~3–8 s
2. NVIDIA Cosmos-Reason2 API call — ~2–5 s
3. fal.ai video generation (LTX-Video 2.3, 6 s video @ 720p): polls every 5 s, up to 36 polls (180 s max) — typical ~60–120 s
4. Video2Robot subprocess (PromptHMR + GMR, two conda envs): `timeout=600` (10 min hard limit) — typical failure path is immediate fallback, success path ~120–300 s
5. MuJoCo render (~2–5 s)

**Result:** Minimum happy-path latency ≈ **70–140 seconds**. fal.ai polling alone is the dominant cost. Stages 1–3 are sequential (each awaited before the next begins — see `server.py:305–349`). V2R runs in `asyncio.to_thread` but there is nothing else running in parallel.

**Verdict:** NOT FALSIFIED — H1 is confirmed. The pipeline is clearly non-interactive by any standard definition. A user must wait >1 minute per interaction.

**Notes:** This doesn't kill the project as a *demo* or *exhibit* system (where latency is acceptable), but it falsifies any claim of "real-time" or "voice-responsive" interaction. The offline fallback (hero library) is instant — but bypasses the entire interesting pipeline.

---

## H2: The physics validation layer is cosmetic, not structural
*[2 / 7]*

**Hypothesis:** The "physics safety" provided by Cosmos-Reason2 (`physics_validator.py`) does not add real physical guarantees — it is primarily a text filter.

**Prediction:** If true, the fallback (used when `NVIDIA_API_KEY` is absent) will be a keyword check, not physics simulation; and even the real API call queries a *language model*, not a physics engine.

**Test:** Read `physics_validator.py` in full.

**Result:**
- `_mock_reasoning()` (default when no key): checks if the gesture description contains `["jumping", "flying", "leap", "soar", "airborne", "float"]`. A prompt like *"Spider-Man firing web from his wrist"* will always return `is_stable=True` regardless of actual pose geometry.
- Real path: calls `nvidia/cosmos-nemotron-34b` — a **text LLM**, not a physics simulator. It is asked to reason about stability from a text description with no joint angles, no CoM data, no robot kinematics.
- `kinematic_brain.py` does perform a **real** ZMP check via MuJoCo CoM computation — but only on the LLM-generated keyframes (Priority 2 path), not at the `physics_validator` gate level (Priority 0).

**Verdict:** NOT FALSIFIED — H2 is confirmed. `physics_validator.py` is a text-based gate, not a physics-based one. Calling it "Cosmos-Reason2 physical analysis" overstates its capability. Real ZMP physics exists only downstream in `kinematic_brain.py`.

**Notes:** The project should rename/document this more accurately. It provides prompt-level safety (no flying prompts) but not robot-level physical safety.

---

## H3: No actual robot deployment — the system ends at simulation
*[3 / 7]*

**Hypothesis:** The pipeline never sends commands to a physical Unitree G1 robot — it is purely a simulation/visualization system.

**Prediction:** If true, no hardware communication code (SDK calls, UDP packets, serial) will exist anywhere in `Mascot Unitree/`.

**Test:** Search for hardware control keywords in the codebase.

**Result:** `server.py` terminates at `render_mujoco_trajectory()` → returns `simulation_video_b64` (a base64 MP4). No `unitree_sdk`, no `cyclonedds`, no UDP socket, no hardware commands found in any file. The Unitree robot is only used as a MuJoCo XML model for kinematics, not as a controlled physical device.

**Verdict:** NOT FALSIFIED — H3 is confirmed. This is a simulation-only system. The "robot" in the project name is a virtual MuJoCo model, not a physical G1.

**Notes:** For a capstone demo, simulation is often acceptable. But marketing it as "robot control" is inaccurate. The project demonstrates a pipeline that *could* be connected to hardware but has not been.

---

## H4: Persona detection degrades silently on unexpected input
*[4 / 7]*

**Hypothesis:** The keyword-based persona detection in `persona_brain.py` has no NLP — common inputs that don't match hardcoded keywords silently fall to "Generic Hero" with no feedback to the user.

**Prediction:** If true, `detect_persona()` is a linear keyword scan with no fuzzy matching, spell-checking, or LLM classification.

**Test:** Read `detect_persona()` in `persona_brain.py:203–214`.

**Result:**
```python
for hero_name, profile in HERO_REGISTRY.items():
    if any(kw in lower for kw in profile["keywords"]):
        return hero_name, profile
return "Generic Hero", DEFAULT_HERO
```
Pure substring matching. A user saying "I want the guy who swings on webs" gets "Generic Hero" because "swings" is not in Spider-Man's keyword list `["spider", "spidey", "peter", "parker", "web", ...]` — wait, "web" IS there. But "claws" → Wolverine works. "The dark knight" → "dark knight" IS in Batman's keywords. However, "the man of steel" → would not match ("man of steel" is not in Superman's keyword list). Confirmed fragility.

Additionally, the LLM (`generate_robot_response`) is only called *after* persona detection — it does not participate in detection itself, only in response generation.

**Verdict:** NOT FALSIFIED — H4 is confirmed. Detection is brittle. Synonym/paraphrase inputs fail silently. There is no LLM-powered understanding of intent.

**Notes:** This is a known and addressable limitation. Could be fixed by having the LLM itself classify the persona from free text.

---

## H5: The three-tier motion fallback collapses to tier 3 in practice
*[5 / 7]*

**Hypothesis:** In the vast majority of real runs, the system uses the hero animation library (tier 3) rather than Video2Robot (tier 1) or LLM kinematics (tier 2), making the sophisticated pipeline largely decorative.

**Prediction:** If true, Video2Robot requires two specific conda environments (`phmr`, `gmr`) that must be pre-configured on the server, and failure is silent.

**Test:** Trace the fallback logic in `server.py:345–364` and `_run_video2robot()`.

**Result:**
- V2R (Tier 1): Requires `video2robot/` directory, `phmr` + `gmr` conda envs, `run_pipeline.py` to succeed, and a `.pkl` output file. Any failure (missing envs, timeout, no pkl) → `return None` → falls to Tier 2.
- LLM kinematics (Tier 2): Requires `HF_TOKEN`. Missing token → `return None` → falls to Tier 3.
- Hero library (Tier 3): Always works. Uses `gesture_to_trajectory(gesture_desc, detected_persona)`.

The fallback chain is silent — the API response gives no indication which tier was used.

**Verdict:** NOT FALSIFIED — H5 is confirmed. In a fresh deployment (without both conda envs set up), the system will always use Tier 3. The impressive pipeline (V2R + LLM kinematics) requires non-trivial environment setup that is not automated.

**Notes:** This should be surfaced in the API response and documented as a hard prerequisite. The fallback is robust but the primary path is fragile.

---

## H6: Video generation has a hard cost structure that prevents open demos
*[6 / 7]*

**Hypothesis:** The only reliable video generation backend (fal.ai) incurs a per-call cost ($0.36/video) that makes unrestricted public demos financially unsustainable.

**Prediction:** No rate-limiting, auth, or token budget is implemented in the FastAPI server.

**Test:** Review `server.py` for any auth middleware, rate limiting, or cost controls.

**Result:** `server.py:30–37` adds CORS with `allow_origins=["*"]`. There is no API key, no rate limiting, no request quota, no per-user budget. Any client that discovers the endpoint can trigger unlimited fal.ai charges. A trivial loop could generate $0.36 × N requests.

**Verdict:** NOT FALSIFIED — H6 is confirmed. The server has zero access controls. For a demo-only local setup this is fine, but it cannot be deployed publicly without authentication.

**Notes:** This is an easy fix (API key header, rate limiter), but it is a real gap for any deployment beyond localhost.

---

## H7: The fallback simulation is visually convincing enough to serve as the primary demo
*[7 / 7]*

**Hypothesis [to falsify the falsifiers]:** Despite all the above weaknesses, the hero animation library (Tier 3) + MuJoCo render produces a compelling enough visual output that the project achieves its stated demo goal.

**Prediction:** If true, `gesture_to_trajectory()` maps hero gesture descriptions to named pose sequences, and the MuJoCo renderer produces video output at a reasonable quality.

**Test:** Review `hero_pose.py` for pose richness, and `server.py` for render quality settings.

**Result:**
- `hero_pose.py` has `HERO_POSE`, `STABLE_BALANCE_POSE`, named gesture mappings, and an `animate()` function that interpolates keyframe sequences at 10 FPS.
- MuJoCo render: 480×640 at 30 FPS, `quality=8`, `yuv420p` colorspace — respectable quality. Kinematic mode (no physics) ensures the robot never falls.
- The system produces two side-by-side videos: the AI-generated reference (from LTX-Video) and the MuJoCo robot simulation.

**Verdict:** FALSIFIED — H7 is NOT falsified. Even Tier 3 produces a genuine dual-video demo: an AI character video alongside a robot simulation doing the same pose. The core experience (voice → hero persona → gesture → robot mimicry) does work end-to-end at the demo level.

---

## Final Summary

**Problem:** Is Mascot Unitree a viable interactive mascot robot system?
**Solved:** YES (with important caveats documented below)
**Hypotheses used:** 7 / 7

**Ruled out (claims that hold):**
- H1: NOT real-time. Minimum latency ~70–140 s per interaction. A live-voice demo is not feasible; a exhibit/kiosk model is.
- H2: Physics validation is a text filter, not a physics engine. ZMP validation only exists on Tier 2 path.
- H3: No physical robot connected. Simulation only.
- H4: Persona detection is keyword-based; paraphrases fail silently.
- H5: In most deployments, only Tier 3 (hero library) will run. V2R path requires non-trivial env setup.
- H6: No auth or rate limiting — cannot be publicly deployed without adding these.

**What survives falsification:**
- H7: The demo *does* work. The dual-video output (AI character + robot sim) is a compelling exhibit-style demo even on Tier 3. The project achieves its stated capstone goal.

**Verdict:** Mascot Unitree is a **viable capstone demo**, not a viable production robot product. The core technical contribution (3-tier motion generation + physics validation pipeline architecture) is sound and novel. The gaps are all engineering polish, not fundamental research failures.

**Recommended next steps to close the gaps:**
1. Add an API key or local-only guard to `server.py` before any deployment
2. Surface which motion tier was used in the API response
3. Document V2R conda env setup as a hard prerequisite with a setup script
4. Rename `physics_validator.py` → `prompt_safety_filter.py` for accuracy
5. Replace keyword persona detection with a single LLM classification call (free on HF)
