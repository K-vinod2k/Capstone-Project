# KPOP: Hardware Deployment Falsification

**Problem:** Will the deployment scripts successfully move the Unitree G1 on real hardware?  
**Budget:** 10 hypotheses  
**Date:** 2026-04-13

---

## H1: Joint ordering in PKL files matches hardware IDL motor indices

**Hypothesis:** The PKL files were built using MuJoCo's actuator index ordering (from scene.xml), which does NOT match the hardware IDL motor ordering — commands will go to wrong joints.

**Prediction:** If false (ordering matches), `model.actuator_trnid` MuJoCo ordering === hardware IDL table in `g1_joint_index_dds.md`.

**Test:** Print MuJoCo actuator index → joint name mapping from scene.xml. Compare against `g1_joint_index_dds.md` 29-DOF table.

**Result:**
```
MuJoCo:  [0]  left_hip_pitch_joint    → Hardware IDL [0] L_LEG_HIP_PITCH   ✓
         [12] waist_yaw_joint         → Hardware IDL [12] WAIST_YAW         ✓
         [13] waist_roll_joint        → Hardware IDL [13] WAIST_ROLL         ✓
         [14] waist_pitch_joint       → Hardware IDL [14] WAIST_PITCH        ✓
         [15] left_shoulder_pitch_joint → Hardware IDL [15] L_SHOULDER_PITCH ✓
         [22] right_shoulder_pitch_joint → Hardware IDL [22] R_SHOULDER_PITCH ✓
         [28] right_wrist_yaw_joint   → Hardware IDL [28] R_WRIST_YAW        ✓
```
All 29 indices match the 29-DOF hardware IDL table exactly.

**Verdict:** FALSIFIED — joint ordering is correct.

**Notes:** PKLs are built against 29-DOF model. Deployment scripts must use 29-DOF robot. 23-DOF IDL has different arm start index (13 not 15).

---

## H2: CRC checksum is computed and set before every LowCmd_ publish

**Hypothesis:** Both `deploy_real.py` and `g1_arm_replay_airborne.py` are missing `cmd.crc = crc.Crc(cmd)` before `publisher.Write(cmd)` — the robot's firmware will silently reject every command.

**Prediction:** If true, searching both scripts for `crc.Crc` will return zero results despite CRC being imported.

**Test:**
```bash
grep "crc.Crc\|cmd.crc" vinod_workspace/deploy_real.py kim_workspace/hardware_deployment/g1_arm_replay_airborne.py
```

**Result:** Zero matches. CRC is imported but never called. Working SDK examples (`stand_go2.py`, `test_unitree_sdk2.py`) all do `cmd.crc = crc.Crc(cmd)` before every Write.

**Verdict:** NOT FALSIFIED — CRC is missing. CRITICAL BUG. Robot will ignore all commands silently.

**Fix:** Added `self._crc = CRC()` to both controllers and `self._cmd.crc = self._crc.Crc(self._cmd)` before every `publisher.Write()` call.

---

## H3: Velocity clamping is actually enforced — max delta ≤ 0.0667 rad/frame

**Hypothesis:** The clamp_pkls.py script produced correct output; no joint moves faster than 2.0 rad/s.

**Prediction:** `max(|diff(joints, axis=0)|) * 30 ≤ 2.0` for all 10 pkl files after clamping.

**Test:**
```
wave                  2.00 rad/s ✓
flex                  1.93 rad/s ✓
punch                 1.99 rad/s ✓
iron_man_repulsor      2.00 rad/s ✓
spider_man_web_shoot   1.96 rad/s ✓
spider_man_landing     1.93 rad/s ✓
captain_america_shield 2.00 rad/s ✓
thor_lightning         2.00 rad/s ✓
hulk_smash             2.00 rad/s ✓
wolverine_claws        2.00 rad/s ✓
```

**Verdict:** FALSIFIED — velocity is clamped correctly on all files.

---

## H4: First frame of each PKL is close to standing pose — ease-in will not snap

**Hypothesis:** First PKL frame has large joint angles that differ greatly from the G1's DAMPING-mode rest position, meaning the 3-second ease-in in deploy_real.py will still cause a violent torque jolt.

**Prediction:** If false, frame[0] of wave_kinematics.pkl has leg joints near the STABLE_BALANCE_POSE values.

**Test:** Print wave pkl frame[0]. Compare to STABLE_BALANCE_POSE.
```
STABLE_BALANCE_POSE:  hip_pitch=-0.3, knee=+0.6, ankle_pitch=-0.3
PKL frame[0]:         joint[0]=-0.3, joint[3]=+0.6, joint[4]=-0.3  ✓
All arm joints at 0.0 (neutral)
```

**Verdict:** FALSIFIED — first frame matches standing pose. Ease-in is safe.

---

## H5: `mode_machine=0` on LowCmd_ header is accepted by G1 firmware

**Hypothesis:** `mode_machine` must be set to a non-zero value for the G1 to accept position commands; 0 causes firmware to reject all motor commands.

**Prediction:** If mode_machine=0 is wrong, the working bridge simulation script (`unitree_sdk2py_bridge.py`) would also fail — but it works.

**Test:** The bridge script receives LowCmd_ messages and applies them to MuJoCo without filtering on mode_machine. The unitree SDK default for G1 uses mode_pr=0 (position reference), mode_machine=0.

**Verdict:** INCONCLUSIVE — can only confirm on real hardware. mode_machine=0 is safe assumption based on SDK defaults. Flag for first hardware run.

---

## H6: `g1_arm_replay_airborne.py` targets correct arm indices for 29-DOF robot

**Hypothesis:** LEFT_ARM = range(15, 22) is wrong — on the physical G1, left arm starts at index 13 (23-DOF layout).

**Prediction:** If hardware is 29-DOF, index 15 = L_SHOULDER_PITCH per IDL table.

**Test:** Cross-reference `g1_joint_index_dds.md` 29-DOF table. Index 15 = L_SHOULDER_PITCH. Index 13 = WAIST_ROLL. The 23-DOF table has arms starting at 13.

**Verdict:** NOT FALSIFIED for 29-DOF robot — indices 15-21 are correct. WOULD FAIL on 23-DOF robot. Confirm hardware version before running.

---

## Final Summary

**Problem:** Will deployment scripts successfully move the G1 on real hardware?  
**Solved:** MOSTLY — one critical bug found and fixed; one requires hardware confirmation.

**Hypotheses used:** 6 / 10

**Bugs found and fixed:**
- **CRC missing** (H2): `cmd.crc = crc.Crc(cmd)` was never called in either deployment script. Added to both. Without this, robot firmware silently ignores every command.

**Ruled out:**
- Wrong joint ordering (H1 — FALSIFIED, ordering matches 29-DOF IDL)
- Unsafe first frame / ease-in snap (H4 — FALSIFIED, first frame is standing pose)
- Velocity too high (H3 — FALSIFIED, all files ≤ 2.0 rad/s after clamping)

**Open — confirm on hardware:**
- `mode_machine` value (H5 — INCONCLUSIVE)
- 23-DOF vs 29-DOF hardware version (H6 — confirm with `g1_encoder_monitor.py` first)

**Before running on robot:**
1. Run `g1_encoder_monitor.py` — confirm arm joints start at index 15 (not 13)
2. Start with `wave` animation, `--interface eth0`, left arm only
3. Watch for "Robot is safe to handle" — confirms CRC fix worked (robot responds)
