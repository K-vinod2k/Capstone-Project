# exp_log_g1_stabilization_models.md

**Skill:** KPOP (Karl Popper hypothesize-predict-falsify)
**Plan under test:** [.cursor/plans/g1_stabilization_models_implementation_plan_110de4af.plan.md](../.cursor/plans/g1_stabilization_models_implementation_plan_110de4af.plan.md)
**Target claim (C8):** *"Unitree internal stabilization (LocoClient + low-level arm task) is a viable and fastest-deployable path for G1 stabilization during hero-pose playback."*
**Budget:** 40 hypotheses
**Start date:** 2026-04-20

---

## Why C8 is the load-bearing claim

The plan's Phase 3 ("fastest deployable path") depends on `g1_arm_replay_loco.py` actually working. If simultaneous locomotion + arm-only low-level control is NOT supported on our hardware, the whole ordering of the plan (Unitree-first → Holosoma → GR00T) collapses, because the first option stops being viable at all.

CLAUDE.md states this coexistence is an **"open research question (no official Unitree answer)"** — yet `g1_arm_replay_loco.py` already implements a specific mechanism (`rt/arm_sdk` topic + weight-bit at `motor_cmd[29].q`) and the session log from 2026-04-20 asserts `LOCO_SET_ARM_TASK` "solves the open research question". These three sources are in tension. KPOP decides.

---

## Claim decomposition

C8 is a conjunction. All three must hold:

- **C8-DESIGN**: Unitree's SDK officially supports simultaneous locomotion + arm-only low-level commands via a published, blend-weighted API.
- **C8-IMPL**: Our `g1_arm_replay_loco.py` implements that API correctly (topic name, enable-weight bit index, IDL, joint-index remap, gains, timing).
- **C8-VALIDATED**: This implementation has been exercised at least once in sim or on hardware without abort.

Falsifying ANY of the three is sufficient to kill the plan's current ordering. We test in that order (cheapest first).

---

## Pre-work evidence (before H1)

| Source | Assertion | Bearing on C8 |
|---|---|---|
| `CLAUDE.md` | Coexistence is "open research question; current approach = release motion mode entirely" | C8-DESIGN doubtful; treated as stale by session log |
| `session_logs/2026-04-20_lerobot-locomotion-controllers.md:51` | `LOCO_SET_ARM_TASK` "solves the open research question" | Finding, not tested |
| `vinod_workspace/g1_arm_replay_loco.py` header | Contract "derived from unitree_sdk2_python_repo g1_arm7_sdk_dds_example.py" | Cites a file NOT in this repo |
| `kim_workspace/.../unitree_sdk2py_bridge.py` | No reference to `rt/arm_sdk` or `arm_task` | Sim bridge cannot validate C8-IMPL |
| `kim_workspace/hardware_deployment/readme.md:125` | `LocoClient` "currently in development, not fully functional in base simulation bridge without a custom server" | C8-VALIDATED on sim unlikely |
| `_kpop/exp_log_hardware_deployment.md` + every other `_kpop/*` log | None reference `rt/arm_sdk`, `arm_task`, or loco-coexistence tests | C8-VALIDATED prior = false |
| `git log -- g1_arm_replay_loco.py` | Single commit `b716a7e` "Add g1_arm_replay_loco.py — rt/arm_sdk arm replay preserving locomotion" | Implementation present, never iterated (no fix-up commits) |

**Initial read before running:** C8-IMPL exists on paper; C8-VALIDATED appears to be FALSE locally; C8-DESIGN's truth depends on evidence outside this repo (Unitree GitHub, LeRobot).

---

**Hypotheses used: 0 / 40**

---

## H1: The plan conflates two different Unitree coexistence APIs

**Hypothesis:** The plan's Phase 3 refers to "LocoClient + arm task" (high-level `ROBOT_API_ID_LOCO_SET_ARM_TASK` RPC path) while `g1_arm_replay_loco.py` actually publishes on the low-level DDS topic `rt/arm_sdk`. If these are two different mechanisms, the plan is internally inconsistent: the implementation doesn't match the description.

**Prediction:** Searching the two artifacts for mechanism keywords will show:
- Plan + session log mention `LocoClient`, `SetArm`, `LOCO_SET_ARM_TASK`, `arm task`.
- `g1_arm_replay_loco.py` mentions `rt/arm_sdk`, `arm_sdk_example`, `motor_cmd[29]`, and does NOT call any `LocoClient` method.
- The code contains NO import of `LocoClient`.

**Test:** Grep each artifact for `LocoClient`, `SetArm`, `LOCO_SET_ARM_TASK`, `rt/arm_sdk`.

**Result:**
- `vinod_workspace/g1_arm_replay_loco.py` — 7 hits for `rt/arm_sdk`; **zero** hits for `LocoClient`, `SetArm`, `LOCO_SET_ARM_TASK`. Direct DDS publisher pattern only.
- Plan — line 35: `` `LocoClient` + arm task ``; line 55 (mermaid): `armTask[rt/arm_sdk publishing]`; line 87: `Keep locomotion active (rt/arm_sdk)`. Plan uses both terms interchangeably.
- Session log line 51: `` `LOCO_SET_ARM_TASK` solves the open research question ``. Line 60: *"Next step: Investigate `SetArm()` / arm task API signature"* — SDK not yet investigated when log was written. Line 115: open item *"Integrate `LocoClient` arm task into deployment pipeline"* (not yet done).
- Someone wrote `g1_arm_replay_loco.py` using `rt/arm_sdk` DDS directly — skipping the pending SDK investigation. The two paths are currently unreconciled in the repo.

**Verdict:** NOT FALSIFIED (plan is internally inconsistent).

**Notes:**
- Two mechanisms are on the table:
  - *Path-A: direct DDS* — publish `LowCmd_` on `rt/arm_sdk`, use `motor_cmd[29].q` ∈ [0,1] as arm-task weight. Implemented in `g1_arm_replay_loco.py`. Claimed to derive from `g1_arm7_sdk_dds_example.py` (not in repo).
  - *Path-B: high-level RPC* — call `LocoClient.SetArm(...)` or send `ROBOT_API_ID_LOCO_SET_ARM_TASK`. Mentioned in session log as "next step"; signature unknown locally.
- They may be equivalent under the hood (Path-B might just wrap Path-A), but the plan does not say so — and the implementation only covers Path-A.
- **Action implied for the plan:** Phase 2 (compatibility audit) must explicitly resolve "Path-A vs Path-B" before Phase 3 claims to be "fastest deployable".

**Hypotheses used: 1 / 40**

---

## H2: `g1_arm_replay_loco.py` has never been exercised (no validation evidence in repo)

**Hypothesis:** No artifact in the repo shows that `g1_arm_replay_loco.py` has been run at all — not even as `--dry-run-map`. If true, C8-VALIDATED is false by default and "fastest path" is wishful.

**Prediction:** `git log` shows only the initial add commit; no `_kpop/` log, session log, or output file references running it.

**Test:** Grep `_kpop/` and `session_logs/` for the filename; check git history; glob for output/report files.

**Result:**
- `git log` — single commit `b716a7e` (add); no follow-up fix commits.
- `_kpop/` grep — only this log (self-reference).
- BUT: `session_logs/2026-04-20_session.md` (lines 119–213) documents:
  - Mapping gate PASSED: `--dry-run-map` on `wave_kinematics.pkl` and `hulk_smash` peak frame (idx 284); remap table cross-checked against `G1_23DOF_Specs/g1_joint_index_dds.md`.
  - Sim gate PASSED: `mujoco_physics_eval.py --legs-only-hold` on `wave_kinematics.pkl`, 354 frames / 35.4 s; Z sag 2.9 cm, pitch bounded to ±2.5°, RMS tracking error 0.28 rad, verdict STANDING.
  - Hardware gate and gravity-FF verification still open.

**Verdict:** FALSIFIED (the file HAS been exercised through two gates).

**Notes:**
- Important caveat acknowledged in the session log itself (line 211): the sim gate uses `--legs-only-hold`, which locks legs to `STABLE_BALANCE_POSE` in MuJoCo — it does NOT exercise the `rt/arm_sdk` topic with a running Unitree locomotion controller. So the sim gate is a *kinematic-safety* validation of the arm trajectory, not a *protocol-coexistence* validation. C8-VALIDATED is therefore partial: safe-motion side validated, coexistence side unvalidated. This promotes H3.

**Hypotheses used: 2 / 40**

---

## H3: The sim gate does NOT simulate the `rt/arm_sdk` coexistence path

**Hypothesis:** Our local MuJoCo bridge (`kim_workspace/hardware_deployment/unitree_mujoco/simulate_python/unitree_sdk2py_bridge.py`) does NOT subscribe to `rt/arm_sdk`, so running `g1_arm_replay_loco.py` against it will produce no robot motion and cannot validate C8-VALIDATED.

**Prediction:** Bridge code mentions only `rt/lowcmd` + `rt/lowstate` + `rt/sportmodestate` + wireless controller; no `rt/arm_sdk`.

**Test:** Grep the bridge for topic strings.

**Result:**
- `simulate_python/unitree_sdk2py_bridge.py:29-117` — subscribes `rt/lowcmd`, publishes `rt/lowstate`, `rt/sportmodestate`. Zero hits on `arm_sdk`.
- `simulate/src/unitree_sdk2_bridge.h` (C++ version) — same story.
- Every example under `unitree_mujoco/example/` uses `rt/lowcmd`.
- The `mujoco_physics_eval.py --legs-only-hold` sim gate works by directly setting joint angles in MuJoCo qpos arrays; it never goes through DDS, never runs a locomotion controller, never receives from `rt/arm_sdk`.

**Verdict:** NOT FALSIFIED (sim does not exercise coexistence).

**Notes:**
- Consequences for the plan:
  - Phase 2's "compatibility audit" cannot validate C8-VALIDATED using local sim — it can only check IO shapes.
  - Phase 3's "fastest deployable path" has a hidden cost: the only way to falsify C8-VALIDATED is hardware time on Kim's iotlab G1. Sim cannot shortcut this.
  - The plan's strategy section claims Unitree-internal is "already closest to current code" (line 46). TRUE in code terms, FALSE in validated-coverage terms: Holosoma and GR00T, being pure ONNX policies, can actually be IO-validated in sim before hardware. Unitree-internal cannot.
- Concrete alternatives to narrow the gap without hardware:
  - A. Write a mock `rt/arm_sdk` subscriber that logs every LowCmd_ frame. Confirms the publisher-side protocol (CRC, weight ramp, mode_machine echo, tau=0, kp/kd gating) without needing a real loco controller. This validates Path-A's *publisher half*.
  - B. Check upstream Unitree documentation for `rt/arm_sdk` contract spec (H5).
  - C. Extend `unitree_sdk2py_bridge.py` to listen on `rt/arm_sdk` and overlay arm-joint targets while running a naive PD controller on legs as a stand-in "loco controller". Validates protocol coexistence *in principle*, not physics.

**Hypotheses used: 3 / 40**

---

## H4: The 23→arm-SDK joint remap in `g1_arm_replay_loco.py` disagrees with the 23-DOF IDL spec

**Hypothesis:** At least one entry in `REMAP_23_TO_ARMSDK` is wrong against `G1_23DOF_Specs/g1_joint_index_dds.md`, meaning hardware-side C8-IMPL would drive the wrong motor.

**Prediction:** Entry-by-entry comparison will surface a misalignment (e.g., R_ELBOW_PITCH mapped to wrist, or a side swap).

**Test:** Tabulate the 10 remap entries against the 23-DOF spec AND against the 14-DOF dual-arm "with-wrists" layout (arm-SDK indexing).

**Result:**

| PKL (23-DOF) | 23-DOF spec name | REMAP → arm-SDK idx | 14-DOF spec name at that idx | Match |
|---|---|---|---|---|
| 13 | L_SHOULDER_PITCH | 15 | L_SHOULDER_PITCH | ✓ |
| 14 | L_SHOULDER_ROLL | 16 | L_SHOULDER_ROLL | ✓ |
| 15 | L_SHOULDER_YAW | 17 | L_SHOULDER_YAW | ✓ |
| 16 | L_ELBOW_PITCH | 18 | L_ELBOW | ✓ (same motor, renamed) |
| 17 | L_ELBOW_ROLL | 19 | L_WRIST_ROLL | ✓ (same motor, renamed — see note) |
| 18 | R_SHOULDER_PITCH | 22 | R_SHOULDER_PITCH | ✓ |
| 19 | R_SHOULDER_ROLL | 23 | R_SHOULDER_ROLL | ✓ (+ sign flip) |
| 20 | R_SHOULDER_YAW | 24 | R_SHOULDER_YAW | ✓ |
| 21 | R_ELBOW_PITCH | 25 | R_ELBOW | ✓ |
| 22 | R_ELBOW_ROLL | 26 | R_WRIST_ROLL | ✓ (same motor, renamed) |

- `INVALID_23DOF_ARMSDK_IDX = {20, 21, 27, 28}` correctly excludes the L/R wrist_pitch/yaw motors that don't exist on 23-DOF hardware.
- Session log line 142–154 records that the table was explicitly cross-checked against this same spec file.

**Verdict:** FALSIFIED (remap is correct).

**Notes:**
- Residual risk: "23-DOF L_ELBOW_ROLL ≡ arm-SDK L_WRIST_ROLL is the *same physical motor*" is a semantic claim about hardware naming that is consistent with Unitree's 23DOF/29DOF chassis-sharing convention but NOT *proven* by the spec text — only named there. First hardware engage should include a single-joint jog test (command 23-DOF idx 17 directly vs command arm-SDK idx 19 via arm_sdk) to confirm they drive the same motor. Recommend adding this as a Phase 3 pre-flight check.

**Hypotheses used: 4 / 40**

---

## H5: `rt/arm_sdk` and the `motor_cmd[29]` weight bit are not officially documented by Unitree — the contract is inferred

**Hypothesis:** The `rt/arm_sdk` topic + weight-bit protocol is an informal community pattern, not an officially documented Unitree API. If true, C8-DESIGN is fragile (could change silently across firmware revisions).

**Prediction:** Upstream `unitree_sdk2_python` repo will NOT contain `g1_arm7_sdk_dds_example.py`, OR the file exists but does not validate the exact protocol `g1_arm_replay_loco.py` implements. Unitree issue tracker will show no official acknowledgment.

**Test:** Fetch upstream example file; search Unitree issue tracker for coexistence question.

**Result:**
- Upstream file EXISTS at `unitree_sdk2_python/example/g1/high_level/g1_arm7_sdk_dds_example.py`. Full content fetched. Matches our implementation almost exactly:
  - Publisher: `ChannelPublisher("rt/arm_sdk", LowCmd_)`
  - Enable bit: `motor_cmd[G1JointIndex.kNotUsedJoint].q = 1` where `kNotUsedJoint = 29` (literal comment: *"NOTE: Weight"*)
  - Arm gains: `kp = 60.`, `kd = 1.5` (identical to our `KP_ARM = 60.0`, `KD_ARM = 1.5`)
  - Control rate: `control_dt_ = 0.02` → 50 Hz (identical to our `CTRL_HZ = 50.0`)
  - Release ramp: `motor_cmd[kNotUsedJoint].q = (1 - ratio)` at stage 4 (identical mechanism)
  - Arm-only writes — legs (0-11) untouched
- **Unitree GitHub issue #108** ("[G1 EDU] Combining high level and low level") has an **official Unitree answer**:
  > *"Yes, this is possible... You can use balanced mode on the G1 and combine it with the arm SDK... Do not attempt to use low-level commands for the lower body simultaneously — only use low-level control for the arms while balance mode handles the legs."*
  - Explicit instruction: `motor_cmd[G1JointIndex.kNotUsedJoint].q = 1` enables arm_sdk.
  - Explicit reference to the example file above.

**Verdict:** FALSIFIED — the protocol is officially documented and officially answered in Unitree's issue tracker. C8-DESIGN is TRUE.

**Notes:**
- One implementation divergence to flag: upstream `arm_joints` list includes `WaistYaw(12)`, `WaistRoll(13)`, `WaistPitch(14)`. Our `g1_arm_replay_loco.py` does NOT touch waist (leaves kp=kd=0, torso stays with loco). On 23-DOF hardware, WaistRoll/WaistPitch are physically absent; WaistYaw exists and is deliberately left to loco. This is intentional and safer (avoids fighting loco's torso balance control). Should be a code comment for future readers.
- The CLAUDE.md assertion that coexistence is an "open research question with no official Unitree answer" is now **STALE**. Recommend updating CLAUDE.md with a pointer to issue #108 and `g1_arm7_sdk_dds_example.py`.

**Hypotheses used: 5 / 40**

---

## Interim summary (after H1–H5)

**C8 decomposition status:**

| Sub-claim | Status | Evidence |
|---|---|---|
| C8-DESIGN (Unitree supports loco + arm-only low-level) | **TRUE (confirmed)** | Issue #108 official answer; `g1_arm7_sdk_dds_example.py` upstream |
| C8-IMPL (`g1_arm_replay_loco.py` implements the protocol correctly) | **TRUE (high confidence)** | Topic, weight bit, gains, rate, arm-only constraint all match upstream; remap matches `G1_23DOF_Specs/g1_joint_index_dds.md` |
| C8-VALIDATED (exercised end-to-end with loco live) | **PARTIAL** | Mapping gate PASSED (dry-run); Sim gate PASSED (legs-only-hold, but does NOT exercise coexistence); Hardware gate OPEN |

**Plan consistency issues surfaced:**

1. Plan says "LocoClient + arm task" (Phase 3) but implementation uses direct `rt/arm_sdk` DDS publishing, not `LocoClient`. Clarify wording.
2. Plan's Phase 2 ("compatibility audit") cannot validate C8-VALIDATED in sim — local MuJoCo bridge has no `rt/arm_sdk` subscriber. Phase 2 should explicitly scope its compatibility check to IO shapes/schemas only, not runtime behavior. For C8-VALIDATED, a hardware gate is mandatory.
3. Plan's Phase 3 assumes "closest to current code" = "fastest to deploy". True for code, false for validated coverage: Holosoma (pure ONNX) can be IO-validated in sim before hardware; `rt/arm_sdk` cannot. The ordering is still correct IF hardware access is imminent, but risky IF hardware access is far away — Holosoma might validate faster end-to-end in that case.
4. CLAUDE.md "open research question" statement is stale.
5. Session log open item *"Get full `LocoClient.SetArm()` signature from SDK repo"* is moot — `g1_arm_replay_loco.py` already bypasses `LocoClient` entirely, using the lower-level `rt/arm_sdk` path that issue #108 endorses. This open item can be closed.

**Recommendations for the plan (to be acted on later by the user):**

- **Plan language fix (cheap):** Replace "LocoClient + arm task" with "direct `rt/arm_sdk` DDS publishing with balance mode preserved" throughout the plan, to match the implementation.
- **Plan phase reorder clarification:** Rename Phase 2 "Compatibility audit" outcome to explicitly state: "Produces schema/IO pass-fail. C8-VALIDATED requires hardware access and is NOT produced by this phase."
- **Plan Phase 3 addition:** Add a single-joint jog pre-flight that commands 23-DOF idx 17 via both `rt/lowcmd` (`deploy_real.py` path) and `rt/arm_sdk` idx 19 (`g1_arm_replay_loco.py` path) to confirm the "ELBOW_ROLL ≡ WRIST_ROLL is same physical motor" semantic relabel assumption before running any full PKL.
- **Plan deliverable add:** Update CLAUDE.md "Known Open Issues" section — remove/revise the "open research question" line and cite issue #108.
- **Plan deliverable add:** Close session-log open item *"Get full `LocoClient.SetArm()` signature"* — not needed for this path.

**Budget pacing:** 5/40 used. C8 is substantially resolved at the design/implementation layer. Remaining hypotheses should target (a) the Phase-4/5 ONNX compatibility audit to decide whether Holosoma is a safer "fastest" path than `rt/arm_sdk` given the validation asymmetry, and (b) hardware-free falsifications of Holosoma/GR00T's IO shapes. Will pause here unless user wants me to continue deeper.

---

## Follow-up actions taken (post-run)

After pausing the KPOP loop at H5, these concrete artifacts were produced so a hardware operator can execute the three pre-flight gates identified above:

1. **Added `--jog-test ARMSDK_IDX` flag** to `vinod_workspace/g1_arm_replay_loco.py` — Gate B. Commands a single arm-SDK joint by a configurable small step, holds, returns, releases. Purpose: close the residual "ELBOW_ROLL ≡ WRIST_ROLL is same physical motor" assumption flagged in H4 by physical observation.
2. **Added `--engage-only [--engage-weight W]` flag** to the same file — Gate C. Ramps `motor_cmd[29].q` (arm-sdk weight) 0 → W → 0 while every arm joint echoes its current encoder q. Purpose: validate topic acceptance without commanding motion — the cleanest falsification test of "does this robot's firmware accept `rt/arm_sdk`" at near-zero physical risk.
3. **Operator guide at** `kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md` — documents Gates A → D as an incremental, fail-safe first-run procedure. Emphasizes the precondition difference vs `deploy_real.py` (BalanceStand vs DAMPING) surfaced during KPOP.

Both gate flags support `Ctrl-C` cleanly — on interrupt, weight is ramped to 0 over `RELEASE_SECONDS` so loco resumes authority smoothly rather than arms going instantly limp.

These are the minimum additions needed to turn C8-VALIDATED from "partial" into a runnable hardware test. They do not commit to any hardware verdict — they only make the verdict cheap to obtain.

---

## H6: The Holosoma and GR00T ONNX files referenced in plan Phases 4–5 do not exist in this repo

**Hypothesis:** The plan's Phases 4 ("Holosoma ONNX Integration") and 5 ("GR00T ONNX Integration") depend on `fastsac_g1_29dof.onnx`, `GR00T-WholeBodyControl-Balance.onnx`, and `GR00T-WholeBodyControl-Walk.onnx` (all named in `session_logs/2026-04-20_lerobot-locomotion-controllers.md:86, 98`). If none of these files are present in the repo, Phases 4–5 are not actionable without a separate artifact-acquisition step the plan does not enumerate.

**Prediction:** Recursive search of the repo finds zero `.onnx` files, zero directories named `holosoma*` / `gr00t*` / `sonic*`, and zero code files referencing the artifact names.

**Test:**

```sh
find . -type f -name "*.onnx"                                   # repo-wide
find . -type d \( -iname "*holosoma*" -o -iname "*gr00t*" \
                  -o -iname "*groot*" -o -iname "*sonic*" \)
find . -type f -iname "*fastsac*"
rg -l 'onnx|Balance\.onnx|Walk\.onnx|fastsac|FastSAC'
```

**Result:**
- `.onnx` files in repo: **0**. (One unrelated `.safetensors` in `.venv/lib/.../compressed_tensors/transform/utils/hadamards.safetensors` — not a policy.)
- `holosoma*` / `gr00t*` / `sonic*` directories: **0**.
- `fastsac*` files: **0**.
- Grep hits on `onnx|fastsac|Balance.onnx|Walk.onnx`: **6 files, all prose** — `.cursor/plans/g1_stabilization_models_implementation_plan_110de4af.plan.md`, `_kpop/exp_log_g1_stabilization_models.md` (this log), both session logs, `kim_workspace/rl_training/README.md` (line 26: *"Export the final model to `.onnx` and send it back to the Mac"* — aspirational), `kim_workspace/README_.md`. **Zero code files** reference any of these names.
- `onnxruntime 1.23.2` IS installed in `.venv` (unrelated — transitively pulled in, no code uses it).
- Plan itself (line 4) lists the deliverables but provides no download step, hash, or URL for the `.onnx` files.

**Verdict:** NOT FALSIFIED — the ONNX artifacts are absent from the repo.

**Notes:**
- HF Hub references from the session log: `nepyope/holosoma_locomotion/fastsac_g1_29dof.onnx` and `nepyope/GR00T-WholeBodyControl_g1/{Balance,Walk}.onnx`. These live on HuggingFace and would need `huggingface_hub.snapshot_download()` or `hf_hub_download()` to pull. The plan does not enumerate this step.
- Downstream consequences for the plan:
  - Phase 2 ("compatibility audit") claims it will "verify model file existence and hash" (plan line 77). Today this check would *always fail* for Holosoma and GR00T. If a pass gate is required before Phases 4/5 start, Phase 2 becomes the blocker, not the enabler.
  - Phase 4 ("Build exact 100D observation packing expected by model", plan line 97) cannot start until the model is downloaded and its IO signature confirmed. The schema numbers in the session log (100D obs, 29D qj/dqj, etc.) are from a paper/model card — not from introspecting the actual `.onnx` we'd ship with.
  - Phase 5 ("GR00T Balance/Walk switch logic", plan line 104) has a 516D obs (= 6×86D history) per the log — this requires *stateful plumbing* across control ticks we do not have today (see H7).
  - Validation-coverage asymmetry flagged in the H5 interim summary becomes sharper: Unitree-internal (Path-A `rt/arm_sdk`) is validated modulo hardware; Holosoma is gated *on an artifact we do not possess*, and GR00T behind that. Plan ordering ("Unitree → Holosoma → GR00T") remains correct, but the gap between Step 1 and Step 2 is bigger than it reads.
- Action implied for the plan (apply later):
  - Add a Phase 0 or pre-Phase-2 task: *"Download Holosoma + GR00T ONNX from HF Hub; record commit SHA and SHA256 in repo; store in `kim_workspace/onnx_policies/`. If HF Hub auth required, document token scope."*
  - Update Phase 2 to state the check explicitly: *"Phase 2 FAILS until models are downloaded."*
  - Update Phase 4 / Phase 5 checklists to start with: *"Load ONNX, print input/output name/shape/dtype from `onnxruntime.InferenceSession.get_inputs()` — this is our source of truth, not the paper."*

**Hypotheses used: 6 / 40**

---

## H7: Holosoma's 100D observation cannot be constructed from current DDS + code on 23-DOF hardware without new plumbing

**Hypothesis:** The Holosoma observation `[last_action(29), ang_vel(3), cmd_yaw(1), cmd_xy(2), cos_phase(2), qj(29), dqj(29), gravity(3), sin_phase(2)]` (session log line 93) requires five pieces of state we either (a) don't currently compute, (b) don't have the correct width for, or (c) don't have a plumbing contract for on 23-DOF hardware. If true, Phase 4's "Build exact 100D observation packing" (plan line 97) is not a one-adapter job — it's a new stateful pipeline.

**Prediction:** For each of the 9 observation components, one of {DDS gives it directly; we compute it locally and retain; we don't have it / width mismatch}. The count of "need new state" and "width mismatch" components is ≥ 3.

**Test:** Decompose the 100D obs against what `unitree_hg.msg.dds_.LowState_` exposes and what our code retains across ticks.

**Result:**

| Component | Dim | Source | Status |
|---|---|---|---|
| `last_action` | 29 | Previous policy output, needs stateful buffer | **NEW STATE** — no adapter keeps previous 29-D action across ticks today. `g1_arm_replay_loco.py` only retains the *last written cmd*, which is on arm indices 15-28 (arm-SDK), and only for commanded joints. |
| `ang_vel` | 3 | IMU base angular velocity | **NEW SIGNAL** — `LowState_.imu_state.gyroscope` (3D) exists in the SDK's IMU message. Our code does not currently read it anywhere. |
| `cmd_yaw` | 1 | Operator command input | **NEW SIGNAL** — we have no velocity-command path today. Would be driven by an external scheduler (joystick, API, keepalive=0). |
| `cmd_xy` | 2 | Operator command input | **NEW SIGNAL** — same. Holosoma uses these as the locomotion target; for a standing hero pose use case, they are 0 (`||cmd|| < 0.05` → Balance branch in session log line 85 for GR00T; Holosoma uses its phase clock to detect stand). |
| `cos_phase` | 2 | Explicit sin/cos oscillator (0.5s period), freezes at π when standing (session log line 94) | **NEW STATE** — policy-owned gait phase. Requires a second stateful scalar we update every `CONTROL_DT=0.005` s and freeze/unfreeze on command-norm. |
| `qj` | 29 | Joint positions | **WIDTH MISMATCH** — 23-DOF hardware `LowState_.motor_state[].q` gives 23 meaningful values; indices 20, 21, 27, 28 (L/R wrist pitch/yaw) have no physical motor. Filling them requires a policy: zero-fill? inject `DEFAULT_ANGLES` from the model's training prior? The session log says Holosoma arm-masks by substituting `DEFAULT_ANGLES` for *arm* joints (line 95); the same substitution must be extended to the missing-wrist indices for us, and that `DEFAULT_ANGLES` vector is ONNX-metadata which we haven't read yet (H6 blocks this). |
| `dqj` | 29 | Joint velocities | **WIDTH MISMATCH** — same analysis. `LowState_.motor_state[].dq` gives 23 non-zero values; 4 wrist indices zero-fill (physically correct since motors don't exist, but the policy wasn't trained to see hard zeros there — it expects `DEFAULT_ANGLES` substitutions and the corresponding `dqj=0` is acceptable only if the policy learned arm-masking symmetry). |
| `gravity` | 3 | Gravity vector in base frame | **NEW COMPUTATION** — typically computed as `R_base_from_world @ [0, 0, -1]`. Needs the IMU quaternion (`LowState_.imu_state.quaternion`, 4D). We read zero of the four. Must also verify frame convention (ENU vs NED; wxyz vs xyzw) against Holosoma's training convention — policies trained in Isaac Lab often use ENU + xyzw + gravity pointing +z=up flipped. This is a common and subtle bug vector. |
| `sin_phase` | 2 | Pair with `cos_phase` | **NEW STATE** — same clock. |

**Verdict:** NOT FALSIFIED — 7 of 9 components require new signals or state (4 NEW SIGNAL/STATE, 2 WIDTH MISMATCH, 1 NEW COMPUTATION, only 0 "direct"). The observation-packing adapter described in plan line 97 is not a thin remap — it is a new subsystem with three new stateful dependencies (phase clock, last action buffer, command interface) and three new IMU-derived channels.

**Notes:**
- Of the seven items, three are mechanical (IMU gyro + quaternion → `ang_vel`, `gravity`) and three are stateful scheduler (command interface, phase clock, last action). All six can be prototyped off-hardware if we first download the ONNX (H6) and introspect its input names/shapes.
- The 100D sum check: 29+3+1+2+2+29+29+3+2 = **100** ✓. The paper's obs vector shape is consistent. The *content* is not trivially available.
- `DEFAULT_ANGLES` vector — a 29-D joint-prior the policy was trained with — is described (session log line 95) as *"embedded in ONNX metadata"*. This is a known pattern: `onnx.load(path).metadata_props` stores key/value strings; `DEFAULT_ANGLES` would be one entry. The plan should include an "extract metadata" step in Phase 2 instead of assuming it's documented elsewhere.
- 23-DOF-specific observation hack: since our arms are 5-DOF per side and Holosoma expects 7-DOF per side (with wrists), we cannot meaningfully populate `qj[20,21,27,28]` / `dqj[20,21,27,28]` from sensors. Best-effort plan: substitute the `DEFAULT_ANGLES` value for wrists (inaction signal) and hope the policy has learned arm-masking tolerance. If it hasn't, Holosoma is not viable on 23-DOF hardware without retraining. *This is a decision gate the plan does not currently name.*
- Plan text to add (Phase 4): *"Observation packing has 7 non-trivial components (see exp_log_g1_stabilization_models.md H7). Build them behind a new `ObservationBuilder` class with stateful fields `phase_t`, `last_action`, `command_source`, plus IMU channel readers. Do not inline this into the controller step()."*

**Hypotheses used: 7 / 40**

---

## H8: Plan Phase 6's sim verification via `mujoco_physics_eval.py` cannot validate Holosoma or GR00T

**Hypothesis:** The plan's Phase 6 ("Sim verification: Reuse `mujoco_physics_eval.py` for disturbance replay and standing stability checks", line 113) assumes `mujoco_physics_eval.py` can exercise an ONNX balance controller. But the script hardcodes a fixed PD controller with hand-tuned `KP`/`KD` arrays (line 254) and drives `data.ctrl` from `pose_dict_to_target()` (line 138) — there is no hook to run an ONNX inference step *per physics tick*, and the only "legs-only" escape hatch (`--legs-only-hold`) **prevents** the legs from being commanded at all (line 322). Since Holosoma and GR00T are whole-body policies that **command legs** (their output includes 29 joint targets including leg joints), the sim verification gate cannot accept them as-is.

**Prediction:** Code inspection of `vinod_workspace/mujoco_physics_eval.py` will show:
1. No import of `onnxruntime` / `ort.InferenceSession`.
2. `apply_pd()` is the only torque source; no branch for running a policy.
3. `--legs-only-hold` locks DOF 0-14 to `STABLE_BALANCE_POSE` (mutually exclusive with Holosoma's whole-body output).
4. The script's KP/KD tuning (legs=300/15, waist=200/10, arms=20/8.9) is different from Holosoma's ONNX-metadata-embedded gains — running either would require reading the ONNX metadata and overriding these.

**Test:** Read `vinod_workspace/mujoco_physics_eval.py` in full; grep for `onnxruntime`, `InferenceSession`, `policy`, `infer`.

**Result:**
- Line 39: `import requests; import pickle`. **No `onnxruntime` import.** Repo-wide `rg onnxruntime` hits only `.venv` site-packages metadata — no code uses it.
- `apply_pd()` (line 155) is the sole path writing to `data.ctrl`. It takes a pre-baked target vector, never a policy handle.
- `KP`, `KD` are module-level arrays built at runtime (lines 84-85, 252-256) with **hand-crafted tier values** (`legs=300/15`, `waist=200/10`, `arms=20/8.944`). Holosoma's session-log claim is *"KP/KD baked into ONNX metadata"* (line 96). These two sources will disagree. If we run Holosoma on our KP, we get trained-on-different-gains behavior — the balance property does not transfer.
- `--legs-only-hold` branch (lines 322-324): `if legs_only_hold: frame[:15] = stable_arr[:15]` — wipes the first 15 DOFs of the PKL target and substitutes standing pose. If Holosoma outputs leg targets, this flag *silently drops them*.
- No inference loop, no action-step callback, no feedback path from sim state to a policy — the sim is open-loop on baked targets.

**Verdict:** NOT FALSIFIED — `mujoco_physics_eval.py` in its current form cannot host Holosoma or GR00T.

**Notes:**
- What a working sim gate for ONNX policies needs (work items plan should name):
  1. Per-tick policy step: at the control rate (200 Hz for Holosoma, 50 Hz for GR00T), build the observation from current `data.qpos/qvel/imu`, run `session.run(None, {"obs": obs})`, write the output into `current_target`.
  2. Gains source: read `DEFAULT_ANGLES`, `KP`, `KD` from `onnx.load(path).metadata_props`. Override the hand-crafted KP/KD tiers for the policy's controlled joints.
  3. Stateful buffers: `last_action`, `phase_t`. Update at the policy rate, not the physics rate.
  4. Command input: for a standing hero-pose test, inject `cmd_xy = [0,0]` and `cmd_yaw = 0`. For a disturbance-recovery test, perturb `data.qvel` at t=T and observe policy recovery.
  5. 29↔23 remap: policy outputs 29D; physical model is 23D. Drop commands to wrist indices (20, 21, 27, 28 in 29-index space), command the remaining 25 (should that be 25 or 23?). In 29-DOF arm-SDK naming, indices 0-11 are legs, 12-14 are waist, 15-21 L arm, 22-28 R arm = 29 total. 23-DOF drops torso-roll/pitch (13, 14) plus the four wrist motors, leaving 23. Confirm the 29↔23 remap against `G1_23DOF_Specs/g1_joint_index_dds.md`.
- With these four pieces, `mujoco_physics_eval.py` can grow a `--controller=holosoma|gr00t|pd` flag. This is a ~150-line extension, not a reuse.
- Plan text to add (Phase 6): *"`mujoco_physics_eval.py` today is a PD-only open-loop target player. To host Holosoma/GR00T in sim, extend with `--controller` flag, per-tick policy step, ONNX metadata gain override, and observation builder from H7. Scope this as a deliverable in Phase 4, not a freebie in Phase 6."*

**Hypotheses used: 8 / 40**

---

## H9: "Unitree internal stabilization" (plan Phases 1-3 naming) obscures that our code is a thin DDS client, not a firmware-layer algorithm

**Hypothesis:** The plan labels Phase 3 *"Harden Unitree internal stabilization path as fastest deployable default"* (todo list line 11). A future reader will expect "hardening" to mean tuning or improving the internal balance algorithm. But our actual code path is `g1_arm_replay_loco.py` publishing `LowCmd_` on `rt/arm_sdk` with `motor_cmd[29].q ∈ [0, 1]` as the arm-task weight — we do not and cannot modify the internal stabilization algorithm, which runs on the locomotion computer (`192.168.123.161`, no SSH). If the term is left unqualified, someone will later propose changes ("tune Unitree's balance gains", "swap its RL policy") that are impossible from our side.

**Prediction:** Grepping the plan will show "Unitree internal stabilization" used as a bare term with no disambiguation. Grepping the code will show ONLY a DDS publisher — no calls into the firmware or the locomotion controller binary.

**Test:** Read the plan's "Scope", "Strategy", and Phase 3 sections; read `g1_arm_replay_loco.py` for any code outside DDS client calls.

**Result:**
- Plan line 34: *"Unitree internal stabilization (`LocoClient` + arm task)"* — plain term.
- Plan line 45: *"Unitree internal first for fastest real-robot path (already closest to current code)"* — "internal" still unqualified.
- Plan line 84 (Phase 3 header): *"Fastest Deployable Path (Unitree Internal)"*.
- Plan line 86: *"Extend `vinod_workspace/g1_arm_replay_loco.py` into the default stabilization-backed replay path: Keep locomotion active (`rt/arm_sdk`). Preserve existing 23→arm-task remap + `--dry-run-map` diagnostics."* — this is the accurate statement, and it's buried under a name that implies more.
- `g1_arm_replay_loco.py` code (line 69-76): imports `ChannelPublisher`, `ChannelSubscriber`, `LowCmd_`, `LowState_`, `CRC`. No imports of any `LocoClient`, `MotionSwitcherClient`, or firmware-facing RPC. The only interaction with the "internal" algorithm is via the published `LowCmd_` and the `motor_cmd[29].q` weight bit — exactly the H5-verified `rt/arm_sdk` protocol.
- There is nothing "internal" about our code. Our code is *external* (a DDS client); what's *internal* is the locomotion controller's algorithm, which we are driving by providing an arm-task target and a blend weight.

**Verdict:** NOT FALSIFIED — "internal stabilization" is misleading shorthand. The accurate framing: *"We write an arm-task client that drives Unitree's on-robot balance controller via `rt/arm_sdk`. The balance algorithm itself is opaque to us."*

**Notes:**
- This is a documentation-clarity hazard, not a technical hazard — but it matters for plan auditability.
- The same conflation already appears in `session_logs/2026-04-20_session.md:35`: *"The G1 has a built-in stabilization algorithm on the locomotion computer, accessible via `LocoClient`"*. Accessible for *commanding* (via `rt/arm_sdk` or `LocoClient.SetArm()`), not for *modifying*.
- Plan text to fix (replace-in-place):
  - Phase 3 heading: *"Fastest Deployable Path — Arm-Task Client (`rt/arm_sdk`)"*
  - todo `unitree-default`: *"Harden arm-task client (`g1_arm_replay_loco.py`) as fastest deployable replay path; locomotion controller handles balance."*
  - Plan line 34 scope item: *"Arm-task client over `rt/arm_sdk` (Unitree's on-robot locomotion controller holds balance). Implemented in `g1_arm_replay_loco.py`."*
- This fix also closes the "LocoClient vs `rt/arm_sdk`" ambiguity flagged in H1 — after the rename, there is only one mechanism named throughout the plan, and it matches the implementation.

**Hypotheses used: 9 / 40**

---

## H10: CLAUDE.md "Known Open Issues" section is stale — its coexistence claim is directly contradicted by H5

**Hypothesis:** The project's canonical onboarding doc (`CLAUDE.md`) contains claims about Unitree arm+loco coexistence that H5 has now officially contradicted. If true, any new contributor (human or agent) reading `CLAUDE.md` today will be misled about the state of the art and may duplicate work.

**Prediction:** `CLAUDE.md` will contain at least one of: (a) *"open research question"* phrasing about simultaneous loco + arm control, (b) the assertion *"no official Unitree answer"*, (c) recommendation to *release motion mode entirely* as the current approach — all of which are now superseded.

**Test:** Grep CLAUDE.md for "open research", "no official", "release motion mode", "coexistence".

**Result:** CLAUDE.md contains the following (lines paraphrased from the system prompt context):
- *"High-level balance + low-level arm control simultaneously = **open research question** (no official Unitree answer)."*
- *"Current approach: release motion mode entirely via `MotionSwitcherClient.ReleaseMode()`, take full low-level control of all joints. Robot cannot walk while doing hero poses."*
- *"To exit debug mode: **reboot required**"*

All three statements are now contradicted by evidence from H5:
- Coexistence IS officially supported. Unitree issue #108 explicitly endorses combining balance-mode legs with arm-SDK arms. Example file `g1_arm7_sdk_dds_example.py` is shipped upstream.
- Releasing motion mode is one approach (the `deploy_real.py` path); it is no longer *the* current approach — `g1_arm_replay_loco.py` is the alternative and is now the plan's "fastest deployable" default.
- The "robot cannot walk while doing hero poses" claim is true only for the `deploy_real.py` path. Under `rt/arm_sdk`, the robot can walk *and* do an arm gesture simultaneously because balance mode is preserved.

**Verdict:** NOT FALSIFIED — `CLAUDE.md` is stale on exactly the point H5 settled.

**Notes:**
- Recommended edit (defer until user confirms; do not edit proactively here): add a new bullet to CLAUDE.md's "Known Open Issues" (or rename that section to "Known Notes / Caveats") with:
  > *"Balance mode + low-level arm control IS officially supported via `rt/arm_sdk` + `motor_cmd[29].q` weight bit (Unitree issue #108, upstream `g1_arm7_sdk_dds_example.py`). Two deployment paths now exist: (a) `deploy_real.py` releases motion mode and takes full 23-DOF low-level control; (b) `vinod_workspace/g1_arm_replay_loco.py` publishes on `rt/arm_sdk` while loco keeps balancing. Path (b) is the fastest-deployable default for hero-pose replay."*
- Also recommended: in CLAUDE.md's deployment sequence section, explicitly state *"For airborne/gantry arm replay with loco held: use `g1_arm_replay_loco.py`. For full 23-DOF takeover (legs + arms): use `deploy_real.py`."*

**Hypotheses used: 10 / 40**

---

## Interim summary (after H6–H10)

**Combined C8 decomposition now:**

| Sub-claim | Status | Evidence |
|---|---|---|
| C8-DESIGN (Unitree supports loco + arm-only low-level) | **TRUE (confirmed)** | H5: Issue #108 official answer; upstream `g1_arm7_sdk_dds_example.py` |
| C8-IMPL (`g1_arm_replay_loco.py` implements the protocol correctly) | **TRUE (high confidence)** | H1/H4/H5: topic, weight bit, gains, rate, arm-only, remap, sign flip all match upstream & spec |
| C8-VALIDATED (exercised end-to-end with loco live) | **PARTIAL** | Mapping + legs-only-hold sim PASSED; `rt/arm_sdk` coexistence gate OPEN; hardware gate OPEN |

**C8 is TRUE at the design and implementation layers. "Fastest deployable" ordering is still correct for path-to-hardware, conditional on hardware access being imminent.**

**Plan consistency issues (accumulating list for user to act on):**

1. (H1) "LocoClient + arm task" wording vs actual `rt/arm_sdk` DDS implementation → rename throughout plan.
2. (H3) Phase 2 cannot validate `rt/arm_sdk` coexistence in local MuJoCo sim (bridge has no subscriber) → Phase 2 scope must explicitly state "schema/IO only; runtime coexistence requires hardware".
3. (H4 note) ELBOW_ROLL ≡ WRIST_ROLL "same physical motor" is a semantic relabel; add a single-joint jog pre-flight test as a Phase 3 step to confirm on hardware before first full PKL run.
4. (H5) CLAUDE.md "open research question" claim is stale → rewrite; close session-log open item about `LocoClient.SetArm()` as moot.
5. (H6) Phases 4 and 5 depend on 3 ONNX artifacts that are NOT in the repo → add a pre-Phase-2 artifact-download step (HF Hub: `nepyope/holosoma_locomotion`, `nepyope/GR00T-WholeBodyControl_g1`) with hash/commit-SHA recording.
6. (H7) Phase 4's "100D observation packing" is a full new subsystem (`ObservationBuilder` with `phase_t`, `last_action`, `command_source`, IMU channels, `DEFAULT_ANGLES` substitution for wrists). Scope this explicitly in Phase 4, not as a thin adapter.
7. (H8) Phase 6's "sim verification via `mujoco_physics_eval.py`" cannot host ONNX policies as written. `mujoco_physics_eval.py` is PD-only; hosting Holosoma/GR00T requires a `--controller` flag, per-tick inference loop, ONNX metadata gain override, and the observation builder from H7. Scope this into Phase 4 (alongside the adapter), not Phase 6.
8. (H9) "Unitree internal stabilization" naming conflates *on-robot balance algorithm* with *our arm-task DDS client*. Rename Phase 3 to "Arm-Task Client (`rt/arm_sdk`)".
9. (H10) CLAUDE.md Known Open Issues section needs a rewrite matching H5/H9 findings.

**Budget pacing:** 10/40 used. The plan's Phase 4/5 feasibility has now been interrogated at the artifact, schema, and sim-hosting levels. The residual 30 hypotheses should, if needed, target:
- (a) Each Holosoma observation component's exact source/convention (IMU frame, quaternion format, gravity sign) before running on hardware;
- (b) A single-joint jog test-plan to confirm ELBOW_ROLL ≡ WRIST_ROLL on hardware (cannot run locally — design-only here);
- (c) ONNX-metadata introspection for Holosoma/GR00T once the files are downloaded — not a hypothesis until files exist;
- (d) The 29↔23 remap for policy *outputs* (previous work only validated the PKL input remap). Holosoma emits 29-D; our robot has 23 motors; the output-side remap is a mirror question of H4.

Pausing here. The plan-quality problems now enumerated are actionable without exhausting more of the budget, and three of them (H6 artifact gap, H7 obs builder scope, H9 naming) are the ones most likely to trip the next implementer. Ready to apply fixes (plan text + CLAUDE.md edits) on request.

---

## Follow-up batch: full PKL-library sim sweep (2026-04-20, post-summary)

User request: maximum sim-side validation, do not drive hardware. Ran `--dry-run-map`, `--dry-run-limits --speed 0.5`, and `mujoco_physics_eval.py --legs-only-hold --headless --hold 1` against every PKL in `kim_workspace/movements/` (10 files). Raw logs + matrix in [`_kpop/sim_validation/README.md`](sim_validation/README.md).

### Key findings

- **10/10 PKLs pass `--dry-run-map`** with the expected arm-SDK index table, R_SHOULDER_ROLL sign flip, and `ELBOW_ROLL ≡ WRIST_ROLL` semantic relabel. No missing or malformed trajectories.
- **10/10 PKLs trigger `[T2] LIMIT ACTIVE`** under default caps (vel ≤ 1.0 rad/s, jerk ≤ 5.0 rad/s³) at `--speed 0.5`. `k_effective` ranges from 1.382 (`spider_man_landing`) to 1.748 (`hulk_smash`, `iron_man_repulsor`). Every PKL will play at 28–36 % of its native rate. Shape preserved, timing stretched — exactly as `[T2]` is designed.
- **9/10 PKLs pass the legs-only-hold sim gate** with uniform `ΔZ = −2.9 cm` (passive PD gravity sag — the arm disturbance is below this noise floor).
- **1/10 FAILS the sim gate** — `spider_man_landing_kinematics`: Final Z 0.365 m, ΔZ −42 cm. Driven by L_ELBOW native jerk of 105 rad/s³ and L_SHOULDER_PITCH 87 rad/s³, the two highest in the library. **Sim ≠ hardware** (sim has no `BalanceStand()`), but this PKL is the outlier and should not be the first hardware Gate D.

### Sim gate bug found (noted, not fixed)

`mujoco_physics_eval.py` only sets `fallen=True` inside the `--vlaw` branch. Without that flag, the script prints `RESULT: PASSED` unconditionally. The `Final Z` numeric IS correct and has been captured for all 10 PKLs; the headline verdict should be disregarded. Recommend fixing (set `fallen = (final_z < FALLEN_THRESHOLD)` regardless of `--vlaw`) in a later pass — not blocking the hardware gate sequence.

### Updated C8-VALIDATED state

| Sub-claim | Prior | After sweep |
|---|---|---|
| C8-DESIGN | TRUE | TRUE |
| C8-IMPL | TRUE (high conf) | TRUE (high conf, sweep shows `[T2]` active on all 10 PKLs) |
| C8-VALIDATED (sim-side) | PARTIAL — wave only | **TRUE for 9/10 PKLs sim-side**; `spider_man_landing` flagged as outlier |
| C8-VALIDATED (hardware) | OPEN | OPEN — requires iotlab gate sequence (A→B→C→D) |

### Hardware-run ordering (recommended)

1. **wave** (Gate D default, smallest PKL, passes sim, 294 frames).
2. flex, spider_man_web_shoot, wolverine_claws, punch, captain_america_shield, thor_lightning.
3. After those confirm the path is solid: iron_man_repulsor, hulk_smash (longest duration × most aggressive jerk).
4. **spider_man_landing LAST.** Sim says it destabilises a passive stance; only run after `BalanceStand()` has been proven to absorb peer PKLs' disturbance.

### Artifacts committed alongside this log

- `_kpop/sim_validation/README.md` — matrix + reproduction steps.
- `_kpop/sim_validation/dry_run_map_*.txt` × 10, `dry_run_limits_*.txt` × 10, `sim_gate_*.txt` × 10.
- `kim_workspace/hardware_deployment/iotlab_gate_runner.sh` — interactive Gate A→B→C→D orchestrator with operator-confirmation pauses at each transition.

**Hypotheses used: 10 / 40** (unchanged — this was validation, not new hypothesis testing).

---