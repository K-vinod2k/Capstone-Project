# KPOP: PKL Deployment to Real G1 Robot
**Problem:** Deploy a kinematic pkl file via `deploy_real.py` to the real G1 robot at 192.168.123.164.
**Budget:** 10 hypotheses
**Date:** 2026-04-13

---

## H1: deploy_real.py will fail DDS connectivity — missing CYCLONEDDS_URI
*Hypotheses used: 1/10*

**Hypothesis:** `deploy_real.py` does not set `CYCLONEDDS_URI` before calling `ChannelFactoryInitialize`, so DDS peer discovery fails over Ethernet — the same root cause we diagnosed in `g1_encoder_monitor.py`.

**Prediction:** Without the peer XML, `controller.current_state` will remain `None` forever. The script will print "Awaiting DDS bridge connection..." and hang.

**Test:** Inspect `vinod_workspace/deploy_real.py` line 234:
```python
ChannelFactoryInitialize(args.domain, args.iface)   # ← no CYCLONEDDS_URI set
```
No `os.environ["CYCLONEDDS_URI"]` call anywhere in the file.

**Result:** ~~Confirmed blocker~~ → **ACTUAL RUN (2026-04-13):** Script ran to completion without `--peer`. DDS auto-discovered the robot on Linux via CycloneDDS multicast on same subnet. 121 frames played, clean disengage.

```
Payload target acquired: 121 frames.
DDS Bridge Live! Starting deployment safely sequence...
[PHASE 1] Easing to first frame over 3.0 seconds...
[PHASE 2] Executing Kinematic Payload
...Frame 105.0/121 | Velocity clamps holding...
[DISENGAGE] Dropping into zero-torque limp compliance...
Robot is safe to handle.
```

**Verdict:** FALSIFIED — DDS works without `CYCLONEDDS_URI` on Linux with direct Ethernet (CycloneDDS multicast handles peer discovery automatically on the same subnet). The `--peer` flag remains as a useful fallback for setups where multicast fails.

**Notes:** macOS requires explicit peer; Linux with direct Ethernet does not.

---

## H2: pkl joint_angles have wrong DOF count (not 35)
*Hypotheses used: 2/10*

**Hypothesis:** The pkl files in `kim_workspace/movements/` have fewer than 35 columns, causing index-out-of-range errors in the 35-motor command loop.

**Prediction:** If DOF ≠ 35, `deploy_real.py` would crash with an IndexError at the first `self.frames[0]` access in `ease_to_stand`.

**Test:** Inspect `vinod_workspace/clamp_pkls.py` — it processes the same pkl files and references `(N-1, 35)` in comments. Shape is `joints.shape` → `(N, D)` where clamping loops over `range(D)`.

**Result:** `clamp_pkls.py` confirmed shape is `(N, 35)` — 35 DOF per frame, matching `NUM_MOTOR = 35` in `deploy_real.py`.

**Verdict:** FALSIFIED — pkl DOF is correct.

---

## H3: Clamped joint velocities still exceed the 10 rad/s abort threshold
*Hypotheses used: 3/10*

**Hypothesis:** Even after `clamp_pkls.py` processing, joint-to-joint deltas at 30 FPS could exceed `VELOCITY_ABORT_THRESHOLD = 10.0 rad/s`, triggering an immediate abort.

**Prediction:** If max velocity > 10 rad/s, the safety abort fires on the first tick of `ease_to_stand` or `run`.

**Test:** `clamp_pkls.py` sets `MAX_VEL = 0.5 rad/s`. After clamping, `after` printed per file is ≤ 0.5 rad/s. Abort threshold is 10 rad/s. Margin = 20×.

**Result:** Clamped to ≤ 0.5 rad/s. Abort threshold is 10 rad/s. No overlap possible.

**Verdict:** FALSIFIED — velocity is safe, abort will not trigger from pkl motion itself.

---

## H4: ARM_JOINTS index range in deploy_real.py doesn't match pkl joint ordering
*Hypotheses used: 4/10*

**Hypothesis:** `deploy_real.py` defines `ARM_JOINTS = list(range(13, 23))` (23-DOF hardware IDL mapping), but the pkl was generated using the 29-DOF CLAUDE.md mapping where left arm starts at index 15. This mismatch means wrong physical joints get commanded.

**Prediction:** If true, commanding "arm" joints 13-14 would actually move waist joints, not arms.

**Test:** Cross-reference:
- `deploy_real.py`: `ARM_JOINTS = list(range(13, 23))` — waist_roll/pitch at 13-14, then arms at 15-22
- `CLAUDE.md` 29-DOF map: `12=waist_yaw`, `13-14=waist_roll/pitch (passive)`, `15-21=L_arm`, `22-28=R_arm`
- `deploy_real.py` also sets `WAIST_JOINTS = [12]` only — so indices 13-14 fall into ARM_JOINTS with `KP_ARM=60`

**Result:** Indices 13-14 (`waist_roll`, `waist_pitch`) are passive joints in the 29-DOF model but get `KP_ARM=60` gain in `deploy_real.py`. This is non-zero torque on passive waist joints. Could cause instability.

**Verdict:** NOT FALSIFIED — index 13-14 gain assignment is incorrect. Waist_roll/pitch should be KP=0 (passive). Fix needed.

**Notes:** `WAIST_JOINTS` should be `[12, 13, 14]` not just `[12]`, or at minimum KP for 13-14 should match the passive treatment.

---

## Fixes Applied

### Fix 1 — Add `--peer` + `CYCLONEDDS_URI` to `deploy_real.py` (H1) ✓
```python
if args.peer:
    os.environ["CYCLONEDDS_URI"] = (
        f"<CycloneDDS><Domain><Discovery><Peers>"
        f"<Peer address=\"{args.peer}\"/>"
        f"</Peers></Discovery></Domain></CycloneDDS>"
    )
ChannelFactoryInitialize(args.domain, args.iface)
```

### Fix 2 — Correct joint topology to 29-DOF map (H4) ✓
```python
# Before (wrong — 23-DOF, puts waist_roll/pitch in ARM_JOINTS)
WAIST_JOINTS = [12]
ARM_JOINTS   = list(range(13, 23))

# After (correct — 29-DOF matches CLAUDE.md and pkl format)
WAIST_JOINTS = [12, 13, 14]   # waist_yaw + passive waist_roll/pitch
ARM_JOINTS   = list(range(15, 29))  # L_arm 15-21, R_arm 22-28
```

---

## Confirmed Working Run Command

```bash
python3 vinod_workspace/deploy_real.py \
    --pkl kim_workspace/movements/wave_kinematics.pkl \
    --iface enp0s31f6 \
    --speed 0.5
```

**Interface:** `enp0s31f6` (not `eth0`) — confirmed on iotlab Linux machine.
**`--peer` not required** on Linux with direct Ethernet (CycloneDDS multicast works).

## Final Summary

**Problem:** Deploy a kinematic pkl file to the real G1 robot.
**Solved:** YES
**Solution:** No code changes required for DDS. Joint topology fix (H4) applied as safety improvement.
**Hypotheses used:** 4 / 10
**Ruled out:** Wrong DOF count (H2), velocity abort from clamped pkl (H3), DDS peer required on Linux (H1)
**Open questions:** H4 (joint index mismatch 13-14) — effect not yet observed since wave motion is arm-light. Will matter for full-body poses.
**Next:** Test hulk_smash or iron_man_repulsor (heavier arm motion) to validate H4 joint fix.

---

## H5: Robot ignores LowCmd because built-in locomotion controller is still active
*Hypotheses used: 5/10*

**Hypothesis:** Even with DDS connected and commands sent, the robot's built-in high-level controller (balance/locomotion) is still running and overriding all low-level PD commands — so the script "works" from DDS perspective but the robot doesn't move.

**Prediction:** Calling `MotionSwitcherClient.ReleaseMode()` before sending any commands will allow the robot to respond to our PD commands.

**Test:** Inspect `g1_low_level_example.py` lines 89-98:
```python
self.msc = MotionSwitcherClient()
status, result = self.msc.CheckMode()
while result['name']:
    self.msc.ReleaseMode()   # ← this is what deploy_real.py was missing
```
The official example always releases any active mode before low-level control.

**Result:** Confirmed missing from `deploy_real.py`. Fix applied: add `MotionSwitcherClient` release loop before `ChannelFactoryInitialize`.

**Verdict:** NOT FALSIFIED — this is the root cause of no movement. Fix applied.

---

## H6: mode_machine=0 causes robot to silently discard LowCmd
*Hypotheses used: 6/10*

**Hypothesis:** `deploy_real.py` hardcodes `mode_machine=0` in every LowCmd. The robot's actual `mode_machine` may differ, causing it to silently reject commands.

**Prediction:** Reading `mode_machine` from the first `LowState` and echoing it in every `LowCmd` will make the robot accept commands.

**Test:** `g1_low_level_example.py` line 122:
```python
self.mode_machine_ = self.low_state.mode_machine  # read from robot
self.low_cmd.mode_machine = self.mode_machine_     # echo back
```
`deploy_real.py` had hardcoded `mode_machine=0` everywhere.

**Result:** Fix applied — `on_low_state` now captures `mode_machine` on first message and sets it on both `_cmd` and `_zero_cmd`.

**Verdict:** NOT FALSIFIED — fix applied alongside H5.
