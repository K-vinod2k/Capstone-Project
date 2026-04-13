# KPOP Log: pickle_to_movement() Validation
**Central Claim:** `pickle_to_movement()` correctly converts any pkl path into robot movement without crashing the STT loop.

**Budget:** 10 hypotheses
**Hypotheses used:** 7 / 10

---

## H1: `None` path crashes the main loop
**Hypothesis:** Passing `None` raises AttributeError on `os.path.exists(None)`.
**Prediction:** Unhandled exception, main loop dies.
**Test:** `pickle_to_movement(None)`
**Result:** Prints `[MOVEMENT] pkl not found: None` — handled by guard.
**Verdict:** FALSIFIED

---

## H2: Missing file path crashes the loop
**Hypothesis:** Non-existent path raises FileNotFoundError.
**Prediction:** Unhandled exception.
**Test:** `pickle_to_movement('./nonexistent.pkl')`
**Result:** Prints `[MOVEMENT] pkl not found:` — handled by guard.
**Verdict:** FALSIFIED

---

## H3: Corrupted pkl (not a dict) crashes the loop
**Hypothesis:** `data.get("joint_angles")` raises AttributeError on non-dict pkl.
**Prediction:** `AttributeError: 'str' object has no attribute 'get'` — main loop dies.
**Test:** Wrote a string pkl, called function.
**Result:** CRASHED with AttributeError — confirmed.
**Verdict:** NOT FALSIFIED — BUG FOUND AND FIXED
**Fix:** Added `isinstance(data, dict)` check + try/except around pickle.load.

---

## H4: pkl with wrong key crashes the loop
**Hypothesis:** Missing `joint_angles` key returns None, then `len(None)` crashes.
**Prediction:** TypeError.
**Test:** pkl with `{'wrong_key': []}`.
**Result:** `[MOVEMENT] Empty or invalid pkl` — handled by existing guard.
**Verdict:** FALSIFIED (after H3 fix)

---

## H5: SemanticSearch returns None for good matches, crashing os.path.join
**Hypothesis:** `query()` condition `if distances[0][0] > 0.5` is inverted — returns only for bad matches, None for good matches.
**Prediction:** `os.path.join(dir, None)` → TypeError in `RobotPersona.forward()`.
**Test:** Queried `wave hello` and `punch attack` — both returned valid filenames.
**Result:** L2 distances in this embedding space are always > 0.5 so the return fires for every query. Logic is fragile but accidentally correct.
**Verdict:** FALSIFIED (for now — fragile, watch if embeddings change)

---

## H6: pkl filenames don't map to ANIMATION_REGISTRY keys
**Hypothesis:** `wave_kinematics.pkl` → `wave_kinematics` → `.replace("_kinematics","")` → `wave` doesn't exist in registry.
**Prediction:** `_replay_sim` prints "not in ANIMATION_REGISTRY" and plays hold baseline.
**Test:** Checked all 10 names against registry.
**Result:** All 10 map correctly (wave, flex, punch, hulk_smash, iron_man_repulsor, spider_man_web_shoot, spider_man_landing, captain_america_shield, thor_lightning, wolverine_claws).
**Verdict:** FALSIFIED

---

## H7: Full pipeline crashes before reaching pickle_to_movement
**Hypothesis:** `RobotPersona.__init__()` downloads `google/gemma-3-1b-it` which is a gated HuggingFace model — fails without auth.
**Prediction:** OSError 401 on any machine without HF_TOKEN + Gemma access approval.
**Test:** `RobotPersona('a Superhero', './movements').forward('punch the enemy')`
**Result:** `OSError: You are trying to access a gated repo. Access to model google/gemma-3-1b-it is restricted.`
**Verdict:** NOT FALSIFIED — BUG FOUND (in Kim's code, not pickle_to_movement)
**Notes:** `pickle_to_movement()` is never reached on a fresh machine without HF credentials. Kim needs to either: (A) request Gemma access at huggingface.co/google/gemma-3-1b-it, or (B) switch to an ungated model (e.g. `Qwen/Qwen2.5-0.5B-Instruct`). The fix is in `robot_persona/src.py` line 54.

---

## Final Summary

**Problem:** Does `pickle_to_movement()` work end-to-end?
**Solved:** YES for the function itself. NO for the full pipeline.
**Hypotheses used:** 7 / 10

**FIXED in pickle_to_movement (main.py):**
1. Corrupted pkl (non-dict) — added isinstance guard + try/except on load

**BUGS FOUND in Kim's code (not our function):**
1. `robot_persona/src.py:54` — `google/gemma-3-1b-it` is a gated model. Crashes with 401 on any machine without explicit HuggingFace approval. **Blocks the entire pipeline from running.**

**Ruled out:**
- None path, missing file, wrong key pkl — all handled
- Animation name mapping — all 10 correct
- SemanticSearch None return — accidentally works (fragile)

**Recommended fix for Kim:**
```python
# robot_persona/src.py line 54 — replace:
model="google/gemma-3-1b-it"
# with ungated model:
model="Qwen/Qwen2.5-0.5B-Instruct"
```
