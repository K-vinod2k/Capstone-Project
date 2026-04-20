# G1 Arm-SDK Gate Runner — Operator Quickstart

**Purpose:** One-page guide to running the four pre-flight hardware gates on the G1 EDU via `iotlab_gate_runner.sh`. Print or keep on a second screen while operating.

**Full procedure:** [`arm_sdk_first_run_guide.md`](arm_sdk_first_run_guide.md). This file is the short version.

---

## 0. Abort rules — read first

Any of these → press **L1+L2 immediately**, then Ctrl-C the runner:

- A joint moves that you didn't expect (especially during Gate B).
- Robot pitches > 5° or starts drifting on its feet.
- Arms jerk or oscillate at engage (Gate C weight ramp).
- Script prints `[VELOCITY ABORT]` or `[EMERGENCY RELEASE]`.
- You hear motor whine / smell heat / see vibration.

Never type `YES` if you didn't visually confirm the gate. A `YES` is your signature.

---

## 1. Pre-flight — before launching the runner

### Physical (you, at the robot)

- [ ] Gantry attached, harness weight-bearing, at least a few cm of slack.
- [ ] ~1.5 m clear radius around the robot (no humans, no obstacles in arm sweep).
- [ ] Pendant in hand. L1+L2 reachable with your dominant thumb.
- [ ] Second person nearby if possible (observer + redundant e-stop).

### Robot state

- [ ] Powered on and booted (~30 s after power).
- [ ] In **BalanceStand**, not damping.
  Sequence: `L2+A` → `L2+B` → press **Start** on pendant.
  Visual check: robot stands on its own, no external support needed.
- [ ] `mode_machine` indicator looks healthy (Gate A will surface this).

### Dev computer (iotlab)

- [ ] SSH'd into the Jetson at `192.168.123.164` (`unitree/123`).
- [ ] `cd` into the repo root.
- [ ] `git pull` — `iotlab_gate_runner.sh` is only in commit `c43b190` and later.
- [ ] Interface name confirmed: `ip link show | grep -E 'UP|enp0s'` — default is `enp0s31f6`.

### On your laptop (Mac) — *already done for you, just reference*

- `--dry-run-map` and `--dry-run-limits` have been run on all 10 PKLs.
  Matrix: [`_kpop/sim_validation/README.md`](../../_kpop/sim_validation/README.md).
- Recommended first PKL for Gate D: **`wave_kinematics.pkl`**.
- **Do NOT** use `spider_man_landing_kinematics.pkl` as first PKL.

---

## 2. Launch

```bash
cd /path/to/Capstone
bash kim_workspace/hardware_deployment/iotlab_gate_runner.sh
```

The script prints:
```
================================================================
 Pre-flight environment check
================================================================
Repo root   : /home/unitree/Capstone
Interface   : enp0s31f6
PKL (Gate D): kim_workspace/movements/wave_kinematics.pkl
Speed (D)   : 0.5
Jog amp (B) : 0.2 rad
Engage wt   : 0.1
...
>>> All operator prerequisites satisfied (gantry, E-stop, BalanceStand)?
>>> Type 'YES' to continue, anything else to abort:
```

Type `YES` only after re-checking the list in section 1.

### Optional overrides (set before launch)

```bash
IFACE=eno1                                                  PKL=kim_workspace/movements/flex_kinematics.pkl           SPEED=0.3                                                   JOG_AMP=0.15                                                ENGAGE_WEIGHT=0.05                                          bash kim_workspace/hardware_deployment/iotlab_gate_runner.sh
```

---

## 3. Per-gate field guide

### Gate A — DDS readback (no actuation)

**Runs:** `g1_encoder_monitor.py --iface $IFACE`

**You watch for:** encoder values printing within 2 s, Joint 13 = L_SHOULDER_PITCH reads plausible, `mode_machine` non-zero.

**When to Ctrl-C:** after ~5 s of clean output. The monitor is read-only; Ctrl-C is expected here.

**Say `YES` if:** values looked sane. **NO** if stream didn't start (→ wrong iface or DDS blocked).

### Gate B — single-joint physical identity (three sub-steps)

Each sub-step is a single arm-SDK index, 0.2 rad amplitude, 3 s weight ramp + 2 s hold + 3 s ease-back.

| # | Command idx | Expect to see |
|---|---|---|
| B.1 | 15 | **Left shoulder pitch** — arm rotates forward/back |
| B.2 | 22 | **Right shoulder pitch** — mirror of B.1 |
| B.3 | 19 | **The motor between L elbow and hand** (labelled `L_WRIST_ROLL` in arm-SDK, is physically `L_ELBOW_ROLL` on 23-DOF) |

**Say `YES` if:** the expected joint, and only that joint, moved ~0.2 rad, then returned. Robot stayed balanced.

**Say `NO` if:** a different joint moved → remap table is wrong for this hardware, do not proceed. Log exactly which joint moved, open a bug with the remap output (run `--dry-run-map` to reproduce the table).

**Say `NO` if:** velocity abort triggered → loco controller is fighting us. Verify BalanceStand was actually engaged. Do not retry at higher amplitude.

### Gate C — engage-only (no arm motion, weight ramp 0 → 0.1 → 0)

**Runs:** `g1_arm_replay_loco.py --engage-only --engage-weight 0.1 --iface $IFACE`

**You watch for:** robot stays balanced. Arms might feel *slightly* stiffer near peak weight — that's the blended arm-SDK authority. No perceptible arm motion. Script prints `[ENGAGE-ONLY] Done.`.

**Say `YES` if:** ramp completed without twitch, no velocity abort, balance held.

**Say `NO` if:** arms twitched on engage (stale encoder read) or loco oscillated (mode mismatch). Gate D is not safe — retry with lower weight (`ENGAGE_WEIGHT=0.05`) or confirm BalanceStand and reboot.

### Gate D — full PKL playback

**Runs:** `g1_arm_replay_loco.py --pkl $PKL --iface $IFACE --speed $SPEED`

The script first re-runs `--dry-run-map` and `--dry-run-limits`. Confirm the output matches what you reviewed on the Mac side.

**Timeline (wave, --speed 0.5):**
- 3 s engage + ease-in to first PKL frame.
- ~28 s of wave playback (effective_speed 0.354 due to `[T2]` jerk cap).
- 3 s ease-out to current encoder q.
- 1 s weight release.

**You watch for:** robot tracks the arm trajectory, stays balanced (torso pitch < 5°), ease-out is smooth. At the end, loco regains full authority and robot continues to balance.

**Say `YES` if:** arms followed the gesture, torso stayed upright, ease-out was smooth, no velocity aborts.

**Say `NO` if:** any of the above fail. The script is already running at conservative `--speed 0.5` with the `[T2]` auto-slowdown; a failure here is a real signal, not a tuning issue.

---

## 4. After all four gates pass

Update these three files — template commits are in [`arm_sdk_first_run_guide.md`](arm_sdk_first_run_guide.md) §Post-run checklist:

- [ ] `_kpop/exp_log_g1_stabilization_models.md` — add hypothesis H11 "C8-VALIDATED confirmed on hardware", mark status CONFIRMED, note PKL used and any anomalies.
- [ ] `session_logs/2026-04-20_lerobot-locomotion-controllers.md` — append "Hardware gates A-D passed on `wave_kinematics.pkl` at `--speed 0.5`".
- [ ] `.cursor/plans/g1_stabilization_models_implementation_plan_*.plan.md` — check off Phase 3's first-hardware item.

Then try a second PKL (see ordering in `_kpop/sim_validation/README.md`):

```bash
PKL=kim_workspace/movements/flex_kinematics.pkl \
  bash kim_workspace/hardware_deployment/iotlab_gate_runner.sh
```

(The runner re-confirms every gate for each PKL. Subsequent runs are much faster since you know the sequence.)

---

## 5. If something goes wrong

### During Gate A–D, runner is active

1. **L1+L2 on pendant** (physical e-stop — always first).
2. Ctrl-C the runner.
3. If robot is still balanced after e-stop release, put it back in damping (L2+B).
4. Record in `session_logs/` and the KPOP log: which gate, what you saw, what you pressed.

### After a failed gate, before retrying

- Read the script output carefully. `g1_arm_replay_loco.py` has a specific velocity abort path that prints joint indices.
- If Gate B failed on a specific sub-step, re-run *only* that sub-step with a smaller amplitude:
  ```bash
  python vinod_workspace/g1_arm_replay_loco.py \
      --jog-test 19 --jog-amp 0.1 --iface enp0s31f6
  ```
- Never escalate amplitude after a velocity abort; always de-escalate.

### If the runner hangs

- `g1_encoder_monitor.py` blocks on a live DDS socket — expected, Ctrl-C frees it.
- If `--engage-only` or `--jog-test` hangs waiting for first LowState for more than 5 s → DDS not flowing. Re-run Gate A to triage.

---

## 6. Commands reference (copy-paste)

```bash
git pull
bash kim_workspace/hardware_deployment/iotlab_gate_runner.sh

PKL=kim_workspace/movements/flex_kinematics.pkl bash kim_workspace/hardware_deployment/iotlab_gate_runner.sh

python vinod_workspace/g1_arm_replay_loco.py --jog-test 15 --jog-amp 0.1 --iface enp0s31f6
python vinod_workspace/g1_arm_replay_loco.py --jog-test 22 --jog-amp 0.1 --iface enp0s31f6
python vinod_workspace/g1_arm_replay_loco.py --jog-test 19 --jog-amp 0.1 --iface enp0s31f6

python vinod_workspace/g1_arm_replay_loco.py --engage-only --engage-weight 0.05 --iface enp0s31f6

python vinod_workspace/g1_arm_replay_loco.py --pkl kim_workspace/movements/wave_kinematics.pkl --iface enp0s31f6 --speed 0.3

python kim_workspace/hardware_deployment/g1_encoder_monitor.py --iface enp0s31f6

python vinod_workspace/g1_arm_replay_loco.py --pkl kim_workspace/movements/wave_kinematics.pkl --dry-run-map
python vinod_workspace/g1_arm_replay_loco.py --pkl kim_workspace/movements/wave_kinematics.pkl --dry-run-limits --speed 0.5
```

---

## 7. Done criteria for this session

- [ ] Gate A passed (DDS flowing).
- [ ] Gate B.1, B.2, B.3 all passed (remap physically validated).
- [ ] Gate C passed (protocol accepted).
- [ ] Gate D on `wave_kinematics.pkl` passed (end-to-end).
- [ ] (Optional) Gate D on one additional PKL.
- [ ] Post-run checklist (section 4) complete.

If all four pass: **C8-VALIDATED is confirmed on hardware.** The plan's Phase 3 unlocks and `rt/arm_sdk` becomes the default deployment path for arm-only replay.
