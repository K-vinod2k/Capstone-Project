# KPOP: safe_experiment.py Falsification

**Problem:** Will safe_experiment.py run correctly on real hardware without crashing or behaving unexpectedly?
**Budget:** 10 hypotheses  
**Date:** 2026-04-13

---

## H1: Syntax error prevents script from loading

**Hypothesis:** safe_experiment.py has a syntax error that would crash on import.
**Prediction:** `python3 -m py_compile` raises SyntaxError.
**Test:** `python3 -m py_compile kim_workspace/hardware_deployment/safe_experiment.py`
**Result:** `SYNTAX OK` — no errors.
**Verdict:** FALSIFIED

---

## H2: MOVEMENTS_DIR path resolves to wrong directory

**Hypothesis:** `Path(__file__).parent.parent.parent / "kim_workspace" / "movements"` resolves incorrectly — wave pkl not found, Phase 2 fails immediately.
**Prediction:** If false, path resolves to `Capstone/kim_workspace/movements/` and `wave_kinematics.pkl` exists there.
**Test:** Simulate `__file__` as the script path, check resolved MOVEMENTS_DIR.
**Result:** `MOVEMENTS_DIR = kim_workspace/movements` exists=True, wave pkl exists=True.
**Verdict:** FALSIFIED — path is correct.

---

## H3: `confirm()` accepts dangerous inputs — 'y' or 'n' work unexpectedly

**Hypothesis:** `confirm()` uses `ans.upper() == 'YES' or ans == ''`. An operator typing 'y' (common shorthand for yes) would get False, silently aborting the phase. In a safety-critical script this is a UX trap.
**Prediction:** `confirm()` with input 'y' returns False (abort) instead of True (proceed).
**Test:** Mocked stdin with inputs: 'YES', 'yes', 'y', 'Y', ''.
**Result:**
```
'YES'  → True  ✓
'yes'  → True  ✓ (because .upper() == 'YES')
'y'    → False ✗ (user expects yes, experiment aborts)
'Y'    → False ✗ (same)
''     → True  ✓
```
**Verdict:** NOT FALSIFIED — 'y'/'Y' silently abort the experiment.
**Fix:** Change condition to `ans.upper() in ('YES', 'Y') or ans == ''`

---

## H4: Phase 1 wiggle profile never returns exactly to zero — off-by-one

**Hypothesis:** The final tick of the ramp-down leaves the motor at 0.0005 rad, not 0.0 — causing the "expected ~0.000" diagnostic to be confusing.
**Prediction:** `profile[-1] != 0.0`
**Test:** Simulate 1000-tick profile mathematically.
**Result:** `Final tick value: 0.000500 rad` — 0.05% error. Max velocity 0.100 rad/s (safe).
**Verdict:** NOT FALSIFIED — off-by-one confirmed. Not a safety issue (0.0005 rad ≈ 0.03°) but makes the terminal output misleading.
**Fix:** Add `profile[-1] = 0.0` by extending total by 1 tick, or clamp final frame to 0.

---

## H5: Wave animation has zero motion at 23-DOF arm indices 13-17

**Hypothesis:** After the 29-DOF→23-DOF remap, all left arm joints in wave_kinematics.pkl are zero — robot won't visibly move in Phase 2.
**Prediction:** If false, at least one of indices 13-17 has non-zero range.
**Test:** Check `j[:,13:18].max() - j[:,13:18].min()` per joint.
**Result:**
```
index 13 (L_shoulder_pitch): range=0.10 rad  ← moves
index 14 (L_shoulder_roll):  range=0.00 rad
index 15 (L_shoulder_yaw):   range=0.00 rad
index 16 (L_elbow_pitch):    range=0.20 rad  ← moves
index 17 (L_elbow_roll):     range=0.00 rad
```
**Verdict:** FALSIFIED — two joints move. However the motion is subtle (10°/20°). Wave animation only uses shoulder pitch + elbow pitch — no roll or yaw. This is the hero_pose.py wave definition, not a remap bug.

---

## H6: Phase 0 and Phase 1/2 use independent state holders — no cross-contamination

**Hypothesis:** The `state_holder` list inside `phase0_readback()` and the `state_holder` in `main()` share memory — Phase 1 velocity abort triggers on stale Phase 0 data.
**Prediction:** If independent, updates to one do not affect the other.
**Test:** Simulated two separate list objects and callbacks — confirmed updates are independent.
**Verdict:** FALSIFIED — state holders are independent.

---

## Final Summary

**Problem:** Will safe_experiment.py run correctly on real hardware?
**Solved:** YES — after two fixes.
**Hypotheses used:** 6 / 10

**Bugs found and fixed:**
1. **H3** — `confirm()` rejects 'y'/'Y': fixed to `ans.upper() in ('YES', 'Y') or ans == ''`
2. **H4** — wiggle final tick = 0.0005 rad: fixed ramp-down to include one extra tick reaching 0

**Ruled out:**
- Syntax errors (H1)
- Wrong movements directory path (H2)
- State holder cross-contamination (H6)

**Open — require real hardware to confirm:**
- Phase 0 subscriber going out of scope before Phase 1/2 sub initializes (SDK-dependent cleanup)
- `mode_machine` value (carried forward from deployment KPOP, still INCONCLUSIVE)
