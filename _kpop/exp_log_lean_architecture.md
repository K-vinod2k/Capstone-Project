# KPOP Log: Lean Architecture Falsification
**Source:** `implementation_plan.md`
**Central Claim:** "A strictly programmatic, parameterized kinematic engine driven by an LLM router can safely and accurately animate the 23-DOF robot without requiring generative video."

**Sub-claims under test:**
- A: The lean path (LLM → hero_pose → MuJoCo) is wired end-to-end today
- B: Latency drops from 30,000ms to <200ms
- C: MuJoCo viewer (`mj_kinematics`) is a sufficient hardware proxy for joint validation
- D: The Cosmos Video / PromptHMR / GMR pipeline is unnecessary for the sprint goal

**Budget:** 6 hypotheses
**Hypotheses used:** 5 / 6

---

## H1: `server.py` never calls `hero_pose.py`

**Hypothesis:** The lean path is NOT wired — `server.py` contains zero references to `hero_pose`, `gesture_to_trajectory`, or any animation function.
**Prediction:** `grep hero_pose server.py` returns empty.
**Test:** `grep -rn "hero_pose|gesture_to_trajectory" vinod_workspace/server.py`
**Result:** Zero matches. `hero_pose.py` is never imported or called by the server.
**Verdict:** NOT FALSIFIED
**Notes:** The lean path exists in `hero_pose.py` as a complete, self-contained module (`gesture_to_trajectory` → fallback router → animation dispatch → lerp_pose frames). It is simply not connected to anything. `server.py` goes directly from persona response to `pipeline.py`.

---

## H2: `pipeline.py` does not exist

**Hypothesis:** `server.py` imports from `pipeline` (line 10) but `pipeline.py` is absent from `vinod_workspace/`.
**Prediction:** `ls vinod_workspace/` shows no `pipeline.py`.
**Test:** Directory listing of `vinod_workspace/`
**Result:** Files present: `hero_pose.py`, `persona_brain.py`, `server.py`, `mujoco_preview.py`, `verify_kinematics.py`, `headless_extraction.py`, `hulk_kinematics.pkl`, `hulk_smash_static.mp4`. No `pipeline.py`.
**Verdict:** NOT FALSIFIED
**Notes:** `server.py` will raise `ModuleNotFoundError: No module named 'pipeline'` on startup. The server is not runnable in its current state. Also: the hardcoded pkl at `output/2026-03-12_07-07-09.pkl` (line 69) does not exist — `output/` directory is absent entirely.

---

## H3: Data format mismatch between `hero_pose.py` output and `mujoco_preview.py` input

**Hypothesis:** `hero_pose.py` animations return `list[dict[str, float]]` (joint name → radians), but `mujoco_preview.py` expects `list[ndarray(35)]` (index-ordered motor array). No adapter exists.
**Prediction:** `animation_iron_man_repulsor()` returns dicts with string keys; `hulk_kinematics.pkl` contains `ndarray (100, 35)`. No name→index mapping exists anywhere in the project.
**Test:**
```
animation_iron_man_repulsor()[0] → {'right_shoulder_pitch_joint': 0.0, ...}  (dict, 10 keys)
pkl['joint_angles'].shape        → (100, 35)  (ndarray)
grep -rn "JOINT_MAP|name_to_idx" → 0 matches
```
**Result:** Confirmed format mismatch. `hero_pose` frames are sparse dicts (only ~10 joints per frame, unordered). MuJoCo expects dense 35-element arrays indexed by motor order. No adapter or mapping table exists.
**Verdict:** NOT FALSIFIED
**Notes:** This is the single implementation gap that must be closed to make the lean architecture work. It requires a `JOINT_NAME_TO_IDX` dict (29 entries from CLAUDE.md map) and a `pose_dict_to_array(frame, n=35)` function that fills zeros for unspecified joints. This is ~15 lines of code and completely unblocked.

---

## H4: Fallback routing latency is well under 200ms (no LLM required)

**Hypothesis:** The keyword fallback path in `_fallback_gesture_mapping()` is fast enough that the lean architecture can hit <200ms end-to-end without any LLM call.
**Prediction:** `_fallback_gesture_mapping()` completes in <1ms; `animation_iron_man_repulsor()` in <1ms.
**Test:**
```python
_fallback_gesture_mapping('point at the ceiling') → 'iron_man_repulsor'  (0.01ms)
animation_iron_man_repulsor() → 24 frames  (0.04ms)
```
**Result:** Routing: 0.01ms. Animation generation: 0.04ms. Total lean path (without LLM): ~0.05ms — 4000x faster than the 200ms target.
**Verdict:** NOT FALSIFIED — claim B is correct for the offline/fallback path.
**Notes:** However, the implementation plan claims the LLM router is in the path. The Qwen2.5-72B call via HuggingFace Inference API adds ~500–2000ms of network latency. The <200ms claim is only valid if the fallback keyword router is used (no HF_TOKEN set), or if `analyze_pose_with_llm()` is bypassed. This needs to be an explicit architectural decision, not an accident.

---

## H5: `mujoco_preview.py` uses `mj_kinematics` — it provides zero physics validation

**Hypothesis:** The plan claims "MuJoCo viewer is perfectly sufficient as a hardware proxy." But `mujoco_preview.py` calls `mujoco.mj_kinematics(model, data)` instead of `mujoco.mj_step()`. This means it is a visual pose-player only — no gravity, no contact forces, no dynamic stability.
**Prediction:** Source inspection of `mujoco_preview.py` line 58 confirms `mj_kinematics`, not `mj_step`.
**Test:** `mujoco_preview.py:58` → `mujoco.mj_kinematics(model, data)` — confirmed.
**Result:** The MuJoCo viewer will display any pose dict that's geometrically valid (no self-collision check either). It will NOT detect:
- A pose that would fall over under gravity
- A pose that violates ZMP stability
- A joint velocity that would overshoot on real hardware
**Verdict:** NOT FALSIFIED — the claim "sufficient as hardware proxy" is **only valid** for the narrow claim of "validates joint angle ranges and visual intent." It is NOT sufficient to validate physical stability.
**Notes:** For the sprint goal (visual demo, MuJoCo confirms the robot *looks right*), this is acceptable. But the plan's language "sufficient as hardware proxy" is too strong. The correct framing: MuJoCo with `mj_kinematics` validates **geometry** (range of motion, self-collision visually). It does NOT validate **dynamics** (balance, ZMP, contact forces). That requires `mj_step` with physics, or the Isaac Lab RL policy.

---

## Final Summary

**Problem:** Does the lean architecture (LLM router → hero_pose → MuJoCo) work end-to-end without the video pipeline?
**Solved:** The logic works. The wiring does not.
**Hypotheses used:** 5 / 6

**What is CONFIRMED true (not falsified):**
- `hero_pose.py` already contains a complete, self-contained lean action engine with 10 hero animations, smooth keyframe interpolation, LLM routing, and keyword fallback.
- The fallback path runs in <1ms total — <200ms latency claim is valid without the LLM call.
- The Cosmos/PromptHMR/GMR pipeline is unnecessary for the sprint goal of visual MuJoCo animation.

**What is BROKEN (falsified by the tests):**
1. `server.py` crashes at startup — `pipeline.py` does not exist (import on line 10).
2. `server.py` never calls `hero_pose.py` — the lean path is unconnected.
3. The hardcoded pkl at `output/2026-03-12_07-07-09.pkl` does not exist — the server's motion step would crash even if it started.
4. No `joint_name → motor_index` adapter exists — `hero_pose` dicts cannot be fed to `mujoco_preview.py` without one.

**Gap inventory to close (in priority order):**
1. Write `JOINT_NAME_TO_IDX` map + `pose_dict_to_array()` adapter — ~15 lines
2. Wire `hero_pose.gesture_to_trajectory()` into `mujoco_preview.py` (replace pkl load with live animation frames)
3. Fix `server.py`: remove `pipeline.py` import, replace with `hero_pose` + `kinematic_brain` path, remove hardcoded pkl reference
4. Decide explicitly: use LLM routing (add ~500ms) or fallback keyword routing (<1ms)?

**Open questions:**
- Is `kinematic_brain.py` (LLM-grounded ZMP-stable trajectories) also functional? That's the tier-2 fallback that could provide physics-aware joint angles without Isaac Lab.
- Does `verify_stability()` from the old pipeline have any equivalent in the lean path, or do we accept that MuJoCo `mj_kinematics` is the only validation?

**Recommended next steps:**
- Agree: strip `server.py` down to `persona_brain → hero_pose → adapter → mujoco_preview`. This is 1 day of wiring work with zero new AI infrastructure.
- Then run the KPOP falsification test from the plan: 5 voice commands through MuJoCo, observe joint outputs visually.
- Only after that: decide whether to add `mj_step` physics for real stability validation.
