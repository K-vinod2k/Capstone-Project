# KPOP Log: Hero Pose Physics Falsification
**Central Claim:** All 10 hero_pose animations are physically viable under gravity in MuJoCo — the robot holds upright (Z > 0.4m) through each one without falling.

**Budget:** 10 hypotheses (1 per animation)
**Hypotheses used:** 10 / 10

---

## Results Table

| Animation | min_Z | max_pitch | Verdict |
|---|---|---|---|
| wave | 0.593m | 42.8° | PASS |
| flex | 0.572m | 45.3° | PASS |
| punch | 0.680m | 30.7° | PASS |
| hulk_smash | 0.391m | 60.1° | **FAIL** |
| iron_man_repulsor | 0.530m | 49.6° | PASS |
| spider_man_web_shoot | 0.596m | 42.5° | PASS |
| spider_man_landing | 0.378m | 11.7° | **FAIL** |
| captain_america_shield | 0.573m | 45.1° | PASS |
| thor_lightning | 0.392m | 59.8° | **FAIL** |
| wolverine_claws | 0.537m | 48.8° | PASS |

FALLEN_THRESHOLD = 0.4m. 7 PASS, 3 FAIL.

---

## H1–H7: wave, flex, punch, iron_man_repulsor, spider_man_web_shoot, captain_america_shield, wolverine_claws

**Hypothesis:** These 7 animations will cause the robot to fall (Z < 0.4m) under physics.
**Prediction:** min_Z < 0.4m for at least one.
**Test:** Headless mj_step() at 500 Hz, 5s hold + animation + 2s return.
**Result:** All 7 hold above 0.4m. min_Z range: 0.530m–0.680m.
**Verdict:** FALSIFIED — these 7 are physically viable.
**Notes:** High pitch angles (30–49°) are acceptable — the robot leans but recovers.

---

## H8: hulk_smash causes a fall

**Hypothesis:** hulk_smash will cause a fall under gravity.
**Prediction:** min_Z < 0.4m.
**Test:** Same headless runner.
**Result:** min_Z = 0.391m, max_pitch = 60.1° — FALLEN (barely, by 9mm).
**Verdict:** NOT FALSIFIED — hulk_smash fails physics.
**Notes:** The overhead bilateral arm slam shifts CoM forward past the ZMP stability margin. The 60° forward pitch is the cause. Fix: reduce max forward lean in `animation_hulk_smash()` keyframes, or add a counterbalancing waist-back angle.

---

## H9: spider_man_landing causes a fall

**Hypothesis:** spider_man_landing will cause a fall under gravity.
**Prediction:** min_Z < 0.4m.
**Test:** Same headless runner.
**Result:** min_Z = 0.378m, max_pitch = 11.7° — FALLEN.
**Verdict:** NOT FALSIFIED — spider_man_landing fails physics.
**Notes:** Low pitch (11.7°) but Z collapses to 0.378m. This is a deep crouch animation — the knee/hip angles drive the pelvis below 0.4m geometrically, not a dynamic fall. Fix: raise the crouch depth in keyframes so pelvis stays above 0.45m, or raise FALLEN_THRESHOLD to 0.35m for crouch-type animations.

---

## H10: thor_lightning causes a fall

**Hypothesis:** thor_lightning will cause a fall under gravity.
**Prediction:** min_Z < 0.4m.
**Test:** Same headless runner.
**Result:** min_Z = 0.392m, max_pitch = 59.8° — FALLEN.
**Verdict:** NOT FALSIFIED — thor_lightning fails physics.
**Notes:** Near-identical failure mode to hulk_smash: one-arm raised overhead shifts CoM laterally + forward past ZMP margin at 59.8° pitch. Fix: reduce arm elevation angle or add waist counter-lean.

---

## Final Summary

**Problem:** Are all 10 hero_pose animations physically viable under gravity?
**Solved:** Partial — 7/10 pass, 3/10 fail.
**Hypotheses used:** 10 / 10

**CONFIRMED VIABLE (7):** wave, flex, punch, iron_man_repulsor, spider_man_web_shoot, captain_america_shield, wolverine_claws

**FAILED (3) + Root Cause:**
1. `hulk_smash` — CoM forward shift at 60° pitch. Fix: reduce forward lean in keyframes.
2. `thor_lightning` — CoM lateral/forward shift at 59.8° pitch. Fix: reduce arm elevation or add waist counter-lean.
3. `spider_man_landing` — Geometric pelvis depth (not dynamic fall). Fix: raise crouch floor in keyframes above 0.45m pelvis height.

**Recommended next steps:**
- For April 13th hardware test: use only the 7 passing + spider_man_landing (fixed) = 8 animations on floor
- hulk_smash and thor_lightning are GANTRY-ONLY: bilateral arm raise + passive waist means CoM cannot be counterbalanced on a floor-standing G1 without RL policy
- Root constraint: waist_pitch is passive (KP=0) on g1_23dof.xml — active counterbalance is impossible in open-loop PD control

**Final floor-safe animation set (8/10):**
wave, flex, punch, iron_man_repulsor, spider_man_web_shoot, spider_man_landing (fixed), captain_america_shield, wolverine_claws

**Gantry-only (2/10):** hulk_smash, thor_lightning
