# Arm-SDK First-Run Guide (G1 EDU, 23-DOF)

> Operator procedure for the **first** hardware test of `vinod_workspace/g1_arm_replay_loco.py`.
> This is the `rt/arm_sdk` path — arms at low-level while the locomotion controller owns
> legs and waist. Different preconditions from `deploy_real.py`; read carefully.

---

## What this procedure validates

`g1_arm_replay_loco.py` has been sim-validated for *arm trajectory kinematics* but NOT for
the `rt/arm_sdk` coexistence protocol — our local MuJoCo bridge has no `rt/arm_sdk`
subscriber. The first hardware run is therefore the first time the publisher-side
protocol (topic, weight bit, CRC, `mode_machine` echo) is tested end-to-end on a
running locomotion controller.

This guide runs four incremental gates. Each gate fails safely (arms go limp at worst)
and each confirms one specific thing before the next unlocks:

| Gate | Validates | Risk if it fails |
|---|---|---|
| **A** — DDS readback | Network, interface, `rt/lowstate` flowing | None (read-only) |
| **B** — single-joint jog | Physical motor identity of the remap | Tiny — one joint, 0.2 rad, soft Kp=60 |
| **C** — engage-only | `rt/arm_sdk` topic accepted by loco | None (arms echo current encoder q, no motion) |
| **D** — wave PKL | Full playback pipeline | Low (gantry, `--speed 0.5`, velocity abort at 8 rad/s) |

**Evidence trail for these gates lives in:**
- [`_kpop/exp_log_g1_stabilization_models.md`](../../_kpop/exp_log_g1_stabilization_models.md) — KPOP validation of the protocol claim (Unitree issue #108 + upstream reference)
- [`session_logs/2026-04-20_session.md`](../../session_logs/2026-04-20_session.md) §4 — sim gate results

---

## Prerequisites

### Hardware
- Unitree G1 EDU, 23-DOF variant
- **Gantry/harness attached and weight-bearing** (suspended or safety-strapped)
- Clear ~1.5 m radius around the robot (no obstacles in arm sweep)
- Controller/pendant in operator's hand for L1+L2 E-stop

### Network (iotlab Linux dev computer)
- Direct Ethernet to the G1's locomotion computer at `192.168.123.161` (dev computer at `192.168.123.164`, SSH `unitree/123`)
- Interface `enp0s31f6` confirmed on iotlab — adjust with `--iface` if yours differs
- CycloneDDS multicast enabled (no `--peer` required on Linux direct)
- `unitree_sdk2_python` installed and importable

### Robot state (CRITICAL — differs from `deploy_real.py`)

| Script | Required robot mode before launch |
|---|---|
| `deploy_real.py` | **DAMPING** (L2+B). Script takes full low-level control. |
| `g1_arm_replay_loco.py` | **BalanceStand** (loco active). Weight bit *blends* arm-SDK authority with the running balance controller. If you launch this in damping mode, arms will be driven against a disengaged loco — behavior is undefined. |

To enter BalanceStand from power-on:
```
L2+A  →  L2+B  (damping)  →  Start()  or controller "Start" button  →  robot stands balanced
```
Confirm visually: robot holds position without external support.

### Pre-flight on your laptop (before going to iotlab)

Both of these run WITHOUT the robot, WITHOUT DDS:

```bash
# Inspect the 23→arm-SDK remap for this PKL
python vinod_workspace/g1_arm_replay_loco.py \
    --pkl kim_workspace/movements/wave_kinematics.pkl --dry-run-map

# Inspect vel/jerk vs caps, see required slowdown
python vinod_workspace/g1_arm_replay_loco.py \
    --pkl kim_workspace/movements/wave_kinematics.pkl --dry-run-limits
```

Expected: `--dry-run-map` shows the symmetric arm pose with R_SHOULDER_ROLL sign flip
applied; `--dry-run-limits` prints a per-joint velocity/jerk table with `k_effective ≤ 1.0`
on `wave_kinematics.pkl` at `--speed 0.5`.

---

## Gate A — DDS readback (no actuation)

Purpose: confirm the dev computer can see `rt/lowstate` from the robot. Fails if the
interface is wrong, CycloneDDS multicast is blocked, or the robot isn't on the same
subnet.

```bash
python kim_workspace/hardware_deployment/g1_encoder_monitor.py --iface enp0s31f6
```

**Pass criteria:**
- Encoder stream prints within 2 seconds
- Joint 13 (L_SHOULDER_PITCH in 23-DOF IDL) reads plausible non-NaN values
- `mode_machine` field is populated (non-zero)

**Fail → fix before Gate B:**
- No stream → wrong `--iface` or DDS blocked; try `ip link show` and rerun on each candidate.
- Stream but NaN values → robot not fully booted or in a fault state; reboot.
- `mode_machine == 0` → robot hasn't entered a valid state yet; complete BalanceStand sequence first.

---

## Gate B — single-joint physical identity jog

Purpose: prove the arm-SDK index → physical motor mapping on THIS robot. The remap
table claims 23-DOF `L_ELBOW_ROLL` (PKL idx 17) ≡ arm-SDK `L_WRIST_ROLL` (idx 19) is
the *same physical motor*. This is plausible from Unitree's 23/29-DOF chassis-sharing
convention but has never been directly jogged on our robot.

**Suggested order** (start with the most unambiguous, work toward the ambiguous one):

| Step | Command                          | Expect to see move      | Confirms |
|------|----------------------------------|--------------------------|----------|
| B.1  | `--jog-test 15 --jog-amp 0.2`    | Left shoulder pitch (arm rotates forward) | L-arm wiring, Δ sign convention |
| B.2  | `--jog-test 22 --jog-amp 0.2`    | Right shoulder pitch     | R-arm wiring, no side swap |
| B.3  | `--jog-test 19 --jog-amp 0.2`    | **The motor between L elbow and hand** (labelled `L_WRIST_ROLL` but is `L_ELBOW_ROLL` on 23-DOF hardware) | The key ELBOW_ROLL ≡ WRIST_ROLL identity |

Run each step:

```bash
python vinod_workspace/g1_arm_replay_loco.py \
    --jog-test 15 --jog-amp 0.2 --iface enp0s31f6
```

Script prompts `Type 'YES' to proceed:` — type `YES` only when the operator confirms
robot is balanced, gantry weight-bearing, E-stop in hand.

**Sequence the script runs:**
1. Waits for first `LowState` (5-second timeout).
2. Ramps `rt/arm_sdk` weight 0 → 1 over 3 s while interpolating the target joint from
   its current encoder q to `q + 0.2 rad`. All other arm joints hold their current q.
3. Holds for 2 s — operator confirms visually which joint moved.
4. Eases back to start q over 3 s.
5. Ramps weight 1 → 0 over 1 s. Loco regains full authority.

**Pass criteria:**
- The joint that physically moves matches the "Expect" column above.
- No velocity abort triggers.
- Robot remains balanced throughout.

**Fail → STOP before Gate C:**
- Different joint moves → the `REMAP_23_TO_ARMSDK` table in `g1_arm_replay_loco.py`
  is wrong for this hardware variant. Do not proceed to Gate C or D. Open a bug.
- Velocity abort triggers on a 0.2 rad step → loco is actively fighting our command.
  Step size should be reduced OR the weight ramp should be slower. Check that the
  robot was in BalanceStand, not damping, at launch.
- Nothing moves → Gate C likely also fails. See troubleshooting below.

---

## Gate C — engage-only protocol test

Purpose: validate that the locomotion controller accepts our `rt/arm_sdk` publications
(topic name, CRC, `mode_machine`, weight bit protocol) WITHOUT commanding any arm
motion. Arms echo their current encoder q every tick while weight ramps 0 → 0.1 → 0.

Only run this after Gate B passes on at least step B.1.

```bash
python vinod_workspace/g1_arm_replay_loco.py \
    --engage-only --engage-weight 0.1 --iface enp0s31f6
```

**Script sequence:**
1. Wait for first `LowState`.
2. Ramp weight 0 → 0.1 over 3 s, commanding each arm joint's current encoder q.
3. Hold at weight = 0.1 for 3 s (observe: no arm twitch, robot stays balanced).
4. Ramp weight 0.1 → 0 over 1 s. Loco regains full authority.

**Pass criteria:**
- Robot stays balanced throughout — no perceptible arm motion, no torso drift.
- No velocity abort.
- Script prints `[ENGAGE-ONLY] Done.` at end.

**Interpretation:**
- Pass = `rt/arm_sdk` publications are accepted and blended with loco. Gate D unlocked.
- Arms go limp at engage = loco handed authority, but our gains didn't hold position.
  Usually means encoder read was stale or timing is off. Retry with slower ramp.
- Arms slightly stiffen and robot continues to balance = ideal PASS.

**Fail → do not run Gate D:**
- Arms jerk on engage → current-q snapshot is wrong. Check `g1_encoder_monitor.py` output.
- Loco fights our commands (oscillation, velocity abort) → topic accepted but mode
  mismatch. Verify robot is in BalanceStand at launch; check `mode_machine` capture
  on launch printout.

---

## Gate D — full wave PKL

Only proceed after Gates A, B, C all pass.

Use `wave_kinematics.pkl` specifically: smallest amplitude in the movements library,
already dry-run-validated, `compute_loco_speed_cap` confirmed within limits at
`--speed 0.5` without slowdown needed.

```bash
python vinod_workspace/g1_arm_replay_loco.py \
    --pkl kim_workspace/movements/wave_kinematics.pkl \
    --iface enp0s31f6 --speed 0.5
```

**Script sequence:**
1. Load PKL, print remap table, print limit report (should show `[WITHIN LIMITS]`).
2. Operator confirms with `YES`.
3. Engage: weight 0 → 1 AND ease from current encoder q to first PKL frame over 3 s.
4. Playback: 50 Hz publish rate, cubic Hermite interpolation between PKL frames.
5. Ease-out: interpolate from last commanded q to current encoder q over 3 s.
6. Release: weight 1 → 0 over 1 s. Loco regains full authority.

**Pass criteria:**
- Robot remains balanced throughout (no fall, no torso pitch > 5°).
- Wave motion executes with both arms (left waves, right at rest or symmetric).
- No velocity abort.
- Script prints `[DONE] arm_sdk released. Locomotion controller has full authority.`

**After the first successful run:**
- Progress to other PKLs in `kim_workspace/movements/` (hulk_smash, captain_america_shield, etc.),
  each with its own `--dry-run-limits` pass first. Some may require lower `--speed`.
- If `--dry-run-limits` reports `k_effective > 1.0`, the script will automatically
  slow down playback to satisfy `--max-arm-vel` / `--max-arm-jerk`. Pose shape
  preserved; timing stretched.

---

## Abort procedures

| Situation | Action |
|---|---|
| Unexpected arm motion at any time | L1+L2 E-stop → investigate before retrying |
| Oscillation or velocity alarm | Script triggers auto-abort at 8 rad/s; you can also Ctrl-C to force ease-out |
| Robot losing balance | L1+L2 E-stop, catch robot via gantry, inspect logs |
| Unclear which gate failed | Stop, read script output, check `_kpop/exp_log_g1_stabilization_models.md` for diagnostic checklists |
| DDS topic not accepted (Gate C) | Confirm BalanceStand, not damping; check `--iface`; verify Unitree firmware version supports `rt/arm_sdk` (all G1 EDU firmwares since 2023-Q2 should) |

---

## Post-run checklist (update after first successful Gate D)

- [ ] `CLAUDE.md` — remove/revise "open research question" line; cite Unitree issue #108 and `g1_arm7_sdk_dds_example.py`.
- [ ] `session_logs/2026-04-20_session.md` — close open items *"Get full `LocoClient.SetArm()` signature from SDK repo"* and *"Integrate `LocoClient` arm task into deployment pipeline"* (not needed — direct `rt/arm_sdk` path is validated).
- [ ] `_kpop/exp_log_g1_stabilization_models.md` — append hardware gate verdicts (A/B/C/D).
- [ ] Plan `.cursor/plans/g1_stabilization_models_implementation_plan_110de4af.plan.md` — mark Phase 3 as hardware-validated; pick up Phase 4 (Holosoma) or Phase 5 (GR00T) next.

---

## Reference

- Unitree official issue #108 — *"[G1 EDU] Combining high level and low level"*: https://github.com/unitreerobotics/unitree_sdk2_python/issues/108
- Upstream reference example: `unitree_sdk2_python/example/g1/high_level/g1_arm7_sdk_dds_example.py`
- 23-DOF joint index spec: [`G1_23DOF_Specs/g1_joint_index_dds.md`](../../G1_23DOF_Specs/g1_joint_index_dds.md)
- Confirmed iotlab deploy sequence for `deploy_real.py` (DIFFERENT preconditions): [`CLAUDE.md`](../../CLAUDE.md)
