# Next Steps — G1 Stabilization Models Plan

**Date:** 2026-04-20
**Preceded by:**
- [`_kpop/exp_log_g1_stabilization_models.md`](./_kpop/exp_log_g1_stabilization_models.md) — KPOP investigation (H1–H10 of 40 budget)
- [`_kpop/sim_validation/README.md`](./_kpop/sim_validation/README.md) — sim sweep across all 10 PKLs in `kim_workspace/movements/`
- [`kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md`](./kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md) — full operator procedure
- [`kim_workspace/hardware_deployment/OPERATOR_QUICKSTART.md`](./kim_workspace/hardware_deployment/OPERATOR_QUICKSTART.md) — one-page field guide

This document is the explicit follow-up list. Items are scoped by when they should happen and what **blocks** them.

---

## Status summary

| Claim | State | Evidence |
|---|---|---|
| C8-DESIGN: Unitree supports `rt/arm_sdk` + weight bit | **CONFIRMED** | Unitree issue #108; upstream `g1_arm7_sdk_dds_example.py` (KPOP H5) |
| C8-IMPL: `g1_arm_replay_loco.py` implements the protocol correctly | **CONFIRMED (high conf)** | KPOP H1/H4/H5; 10/10 PKLs pass `--dry-run-map` |
| C8-VALIDATED (sim-side) | **TRUE for 9/10 PKLs** | `_kpop/sim_validation/` — all PKLs pass `[T2]`; only `spider_man_landing` sim-falls |
| C8-VALIDATED (hardware) | **OPEN** | Needs Gate A→B→C→D on iotlab |

Plan's Phase 3 ordering ("Unitree-first") is therefore correct conditional on hardware access.

---

## 1. Immediate — today / next iotlab session

**Owner:** operator at iotlab. **Blocker for everything in Section 2+.**

### 1.1 Run the four hardware gates on `wave_kinematics.pkl`

1. SSH to iotlab dev computer:
   ```bash
   ssh unitree@192.168.123.164
   cd /path/to/Capstone
   git pull
   ```
2. Put robot in `BalanceStand` (L2+A → L2+B → Start on pendant). Gantry loaded. L1+L2 in hand.
3. Run the interactive gate runner:
   ```bash
   bash kim_workspace/hardware_deployment/iotlab_gate_runner.sh
   ```
4. Type `YES` between each gate **only after** visually confirming per [`OPERATOR_QUICKSTART.md`](./kim_workspace/hardware_deployment/OPERATOR_QUICKSTART.md) §3.

**Success criteria:**
- Gate A: encoders stream within 2 s, `mode_machine` non-zero.
- Gate B.1 (idx 15): **only** left shoulder pitch moves ~0.2 rad.
- Gate B.2 (idx 22): **only** right shoulder pitch moves ~0.2 rad.
- Gate B.3 (idx 19): **only** the motor between L elbow and hand moves ~0.2 rad. This physically confirms `23-DOF L_ELBOW_ROLL ≡ arm-SDK L_WRIST_ROLL` (KPOP H4's open hardware check).
- Gate C: no arm twitch on engage ramp, robot stays balanced.
- Gate D: wave plays end-to-end, torso pitch < 5°, ease-out smooth, no velocity aborts.

### 1.2 Run Gate D on two additional PKLs

After 1.1 passes, you don't need to re-run A/B/C. Direct Gate D on the next safest PKLs per the ordering in [`_kpop/sim_validation/README.md`](./_kpop/sim_validation/README.md#recommended-hardware-first-run-ordering):

```bash
python vinod_workspace/g1_arm_replay_loco.py \
    --pkl kim_workspace/movements/flex_kinematics.pkl \
    --iface enp0s31f6 --speed 0.5

python vinod_workspace/g1_arm_replay_loco.py \
    --pkl kim_workspace/movements/spider_man_web_shoot_kinematics.pkl \
    --iface enp0s31f6 --speed 0.5
```

**Do not run** `spider_man_landing_kinematics.pkl` in this session — it is the only sim-FAIL (Final Z 0.365 m) and must be gated behind at least 9 other successful PKLs.

### 1.3 Post-run updates (after all gates pass)

Append to the KPOP log a hypothesis H11 "C8-VALIDATED confirmed on hardware for wave + flex + spider_man_web_shoot" with the raw script output pasted in. Template location in `_kpop/exp_log_g1_stabilization_models.md` — follow the existing H6–H10 format.

Close the item in `session_logs/2026-04-20_lerobot-locomotion-controllers.md` ("Hardware gate status") by flipping each gate from `not yet run` to `passed YYYY-MM-DD HH:MM` with the PKL name.

Mark Phase 3's first-hardware checkbox complete in `.cursor/plans/g1_stabilization_models_implementation_plan_110de4af.plan.md`.

---

## 2. This week — library expansion + known bug fixes

**Blocker:** §1 complete (hardware path proven).

### 2.1 Full PKL library sweep on hardware

Run Gate D on the remaining seven PKLs, in the order from the sim-validation matrix. One per day or one per hour depending on throughput. Record per-PKL in `session_logs/`:

- `wolverine_claws` → `punch` → `captain_america_shield` → `thor_lightning` → `iron_man_repulsor` → `hulk_smash` → `spider_man_landing` (last).

After each, note: did `[T2]` slowdown feel appropriate? Any torso pitch excursions? Any velocity aborts?

### 2.2 Fix `mujoco_physics_eval.py` PASSED-regardless-of-Z bug

Found during the sim sweep: `fallen` is only set to `True` inside the `--vlaw` branch. Without that flag, `RESULT: PASSED` prints regardless of `Final Z`. The `Final Z` numeric is correct — only the headline verdict is wrong.

**Fix:**
```python
# In vinod_workspace/mujoco_physics_eval.py around line 476:
if not fallen:
    fallen = final_diag["z"] < FALLEN_THRESHOLD
```
Then verdict/print logic uses the same `fallen` flag. Add a one-line regression test: run on `spider_man_landing` and assert verdict = `FAILED`.

### 2.3 Add `SKIP_ABC=1` env toggle to the gate runner

Right now `iotlab_gate_runner.sh` re-runs Gates A/B/C every invocation. For operators running multiple PKLs in one session, this is wasteful. Add:

```bash
if [ "${SKIP_ABC:-0}" != "1" ]; then
    gate_A; gate_B; gate_C
else
    echo "[SKIP_ABC=1] Skipping Gates A/B/C; operator asserts they passed earlier this session."
    confirm "Confirm Gates A/B/C PASSED earlier this session?"
fi
gate_D
```

Use case: `SKIP_ABC=1 PKL=kim_workspace/movements/thor_lightning_kinematics.pkl bash iotlab_gate_runner.sh` for the 4th PKL of the day.

### 2.4 Hook up right arm in `main.py` and `example.py`

Known open issue per CLAUDE.md §"Known Open Issues":

> Both `_replay_hardware()` functions import and use only `LEFT_ARM` from `g1_arm_replay_airborne`. Pass `LEFT_ARM + RIGHT_ARM` to `ArmReplayController` to enable both arms.

Find the two call sites (grep for `LEFT_ARM` in `main.py` and `example.py`), change to `LEFT_ARM + RIGHT_ARM`. Test via `--text "Hulk smash!"` with robot on gantry — verify both arms command.

### 2.5 Add ease-out to `deploy_real.py`

Known open issue per CLAUDE.md. Currently after playback the script drops to zero torque (limp), which stresses joints. Mirror the ease-out in `g1_arm_replay_loco.py`: interpolate last commanded q → neutral over 2 s, then zero-torque.

Reference implementation:
```python
# In deploy_real.py, after playback loop:
for step in range(int(2.0 * CTRL_HZ)):
    alpha = step / (2.0 * CTRL_HZ)
    for j in range(35):
        cmd.motor_cmd[j].q = (1 - alpha) * last_q[j] + alpha * 0.0
    publisher.Write(cmd)
```

---

## 3. Short-term — close KPOP plan inconsistencies (H1–H10)

**Blocker:** none. These are doc edits that can happen in parallel with §2.

From the KPOP log's accumulating list (`_kpop/exp_log_g1_stabilization_models.md` §Interim summary):

### 3.1 (H1) Rename "LocoClient + arm task" → `rt/arm_sdk` throughout plan

The plan currently describes the coexistence mechanism with two different names interchangeably. Grep the plan file for `LocoClient + arm task`, `armTask[`, `LOCO_SET_ARM_TASK`, and rewrite each to either `rt/arm_sdk arm-SDK client` (when referring to the DDS topic) or `LocoClient.BalanceStand()` (when referring to the on-robot balance controller). These are two distinct things.

### 3.2 (H3) Scope Phase 2 explicitly

Add to Phase 2 of the plan:
> **Scope note:** Our local MuJoCo bridge does not subscribe to `rt/arm_sdk`. Phase 2 validates trajectory kinematics (joint limits, velocity, jerk, leg-lock stability) only. Runtime `rt/arm_sdk` coexistence with the real locomotion controller cannot be validated in sim and requires hardware (Phase 3 Gates A–D).

### 3.3 (H4) Add Gate B.3 as explicit Phase 3 step

Add to Phase 3's first-hardware checklist:
> Before first full PKL run, jog arm-SDK idx 19 (L_WRIST_ROLL/L_ELBOW_ROLL) at 0.2 rad amplitude via `--jog-test 19` and visually confirm the elbow-roll motor moves, not a wrist motor. This physically validates the 29→23 semantic relabel.

### 3.4 (H5/H10) Update CLAUDE.md "Known Open Issues"

Already partially done in commit `c43b190` (the "open research question" bullet is gone). Remaining: add explicit cross-references from the `deploy_real.py` and `g1_arm_replay_loco.py` sections to [`arm_sdk_first_run_guide.md`](./kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md).

### 3.5 (H6) Add pre-Phase-2 artifact download step

Phases 4 and 5 depend on ONNX artifacts not currently in the repo:
- `nepyope/holosoma_locomotion` (HF Hub)
- `nepyope/GR00T-WholeBodyControl_g1` (HF Hub)

Add a new Phase 0 or pre-Phase-2 section to the plan:
> Before Phase 4 work begins, run `huggingface-cli download nepyope/holosoma_locomotion` and `huggingface-cli download nepyope/GR00T-WholeBodyControl_g1`. Record the commit SHA and checksum in `_kpop/artifact_manifest.md`. Phase 4 and 5 blocks on artifacts being resolvable.

### 3.6 (H7) Scope `ObservationBuilder` into Phase 4

Phase 4 currently describes "100D observation packing" in one line. It's a full subsystem:
- `phase_t` (scalar, gait-phase clock)
- `last_action` (19-D, previous tick's policy output)
- `command_source` (3-D velocity command or 6-D pose command)
- IMU channels (3 gyro + 3 accel + 4 quat)
- `DEFAULT_ANGLES` substitution for wrist positions (the 23-DOF robot has no wrist_pitch/yaw motors; policy expects 29-D inputs — fill unused with neutral)

Add a sub-deliverable `ObservationBuilder` class to Phase 4 with unit tests against a known Isaac Lab observation tuple.

### 3.7 (H8) Fix `mujoco_physics_eval.py` to host ONNX policies

Current state: PD-only. Phase 6 as written cannot sim-verify Holosoma/GR00T. Add a `--controller {pd,holosoma,groot}` flag that:
- For `pd`: existing path.
- For ONNX policies: load via `onnxruntime`, run inference at policy rate (50 Hz for Holosoma), read per-tick observation from `ObservationBuilder`, clamp output via ONNX metadata's declared action range.

Scope this into Phase 4 (alongside the builder), not Phase 6. Phase 6 then just runs it.

### 3.8 (H9) Rename Phase 3

Currently: "Unitree internal stabilization". This conflates the on-robot Unitree balance controller with our client. Rename: "Arm-Task Client (`rt/arm_sdk`)".

---

## 4. Medium-term — Phase 4 / 5 prep

**Blocker:** §3.5 (artifacts downloaded) + §3.6 (observation builder design) + §3.7 (sim host for ONNX).

### 4.1 Validate 29↔23 remap for policy *outputs*

KPOP H4 validated the remap for PKL *inputs*. Holosoma and GR00T output 29-D or 19-D action vectors. We need the mirror question answered: which output indices map to which hardware motors?

Action: after artifact download (§3.5), introspect ONNX metadata. Check the `action_joint_names` field (or equivalent) against our `G1_23DOF_IDL` list in `G1_23DOF_Specs/g1_joint_index_dds.md`. Document the remap in a new `_kpop/exp_log_policy_output_remap.md`.

### 4.2 Holosoma first sim run

Once §3.5/§3.6/§3.7/§4.1 are done:
```bash
.venv/bin/python vinod_workspace/mujoco_physics_eval.py \
    --controller holosoma \
    --holosoma-onnx <path> \
    --headless --hold 2
```
Expected: robot stands on its own (Holosoma IS a locomotion policy, unlike our PKLs). If it falls, the issue is observation building or output remap, not the policy.

### 4.3 GR00T-WBC first sim run

Same pattern. GR00T is a full whole-body policy; it will behave differently from Holosoma (it actively tracks upper-body commands, which Holosoma does not). Expect mid-air-tracking experiments, not just standing.

---

## 5. Ops + tooling

**Blocker:** none. Parallel with other sections.

### 5.1 Canonicalize PKL sources

`kim_workspace/movements/` holds the 10 hero-animation PKLs, all clamped to 2.0 rad/s. `Pkl files/` at repo root holds raw video2robot exports (e.g. `2026-03-12_07-15-35.pkl`, 1400 rows — likely a dance capture). These have **not** been through `clamp_pkls.py` or the sim sweep.

Proposal:
- Rename `Pkl files/` → `vinod_workspace/video2robot_exports/` (clearer provenance).
- Add to `vinod_workspace/clamp_pkls.py`: a `--source` flag that reads from `video2robot_exports/`, clamps + validates, writes to `kim_workspace/movements/` with a standardized name.
- Write a sibling `vinod_workspace/validate_pkl.py` that runs `--dry-run-map` + `--dry-run-limits` + the headless sim gate and prints a single-line verdict (pass/fail/warn).

### 5.2 CI for new PKLs

Add a GitHub Action: on any PR that touches `kim_workspace/movements/*.pkl`, run `validate_pkl.py` against each changed file and fail the PR if any FAILS. This catches regressions like a video2robot pipeline update pushing out PKLs with impulsive jerks.

### 5.3 Gate runner logging

`iotlab_gate_runner.sh` output currently goes to stdout only. Add `tee`:
```bash
LOG="session_logs/gate_run_$(date +%Y%m%d_%H%M%S).log"
main "$@" 2>&1 | tee "$LOG"
```
Post-mortems then have a full timestamped record.

### 5.4 Fix missing `run_gemma.py` tracking

Repo has an untracked `run_gemma.py` at the root. Either commit it (document what it does) or delete it. Rule of thumb: untracked scripts at repo root bitrot.

---

## 6. KPOP budget remaining

10 of 40 hypotheses used. Residual budget earmarked for:
- (a) Holosoma observation-component conventions (IMU frame, quaternion format, gravity sign) — before running §4.2.
- (b) Single-joint jog hardware verdict for Gate B.3 (reserved for post-§1.1).
- (c) ONNX metadata introspection for Holosoma/GR00T — runs once §3.5 is done.
- (d) 29↔23 output remap — §4.1.

Plan is to use these five-at-a-time as Phase 4 unblocks; don't pre-spend.

---

## 7. Priority stack

If you can only do one thing per day:

| Day | Item | Unblocks |
|---|---|---|
| Today | §1.1 — Gates A–D on wave | Everything |
| Today | §1.2 — Gate D on flex + spider_man_web_shoot | Confidence for §2.1 |
| Day 2 | §1.3 — Post-run artifact updates | §3 doc work |
| Day 3 | §2.2 — Fix `mujoco_physics_eval.py` verdict bug | Better sim signal for new PKLs |
| Day 4 | §2.4 — Right-arm fix in main.py/example.py | Full-body persona demos |
| Day 5 | §3.5 — Artifact download | Phase 4/5 unblocked |
| Week 2 | §3.1–3.8 — Plan language cleanup | Clear onboarding for next implementer |
| Week 2 | §4.1 — Policy output remap | Phase 4 first sim |
| Week 3 | §4.2 — Holosoma sim run | First non-PKL policy on-robot path |

---

## Done criteria for this roadmap

**Roadmap closed when:**
- All 10 PKLs in `kim_workspace/movements/` have been run on hardware at `--speed 0.5` without velocity abort.
- `_kpop/exp_log_g1_stabilization_models.md` has an H11 confirming C8-VALIDATED on hardware.
- Plan document (`.cursor/plans/g1_stabilization_models_implementation_plan_*.plan.md`) is consistent with the `rt/arm_sdk` naming (H1), Phase 2 scope (H3), Phase 3 Gate B.3 checklist (H4), CLAUDE.md cross-references (H5/H10), artifact manifest (H6), Phase 4 `ObservationBuilder` + ONNX host (H7/H8), and Phase 3 rename (H9).
- Holosoma can stand in sim (§4.2).
- GR00T-WBC can track a command in sim (§4.3).

At that point, the plan's Phase 3 is fully validated and Phase 4/5 can begin in earnest.
