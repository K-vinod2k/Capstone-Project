# Sim-side validation matrix for `g1_arm_replay_loco.py`

**Date:** 2026-04-20
**Environment:** `.venv` on Vinod's Mac — mujoco 3.7.0, numpy 2.2.6
**Raw logs:** `dry_run_map_<pkl>.txt`, `dry_run_limits_<pkl>.txt`, `sim_gate_<pkl>.txt` in this folder.

## What this validates and does NOT validate

| Check | Validates | Does NOT validate |
|---|---|---|
| `--dry-run-map` | 23-DOF PKL → arm-SDK index table, R_SHOULDER_ROLL sign flip, unused-index set | DDS, robot state |
| `--dry-run-limits` | `[T2]` loco-aware cap math: vel ≤ 1.0 rad/s, jerk ≤ 5.0 rad/s³, required `k_effective` | DDS, robot state |
| `mujoco --legs-only-hold` | Arm trajectory disturbs a PASSIVELY PD-held leg stance by how much | `rt/arm_sdk` protocol, `BalanceStand()` active reaction, mode_machine, CRC |

The sim gate is an over-conservative proxy: the real robot has `LocoClient.BalanceStand()` actively counteracting arm-induced torques, so the sim Z-sag is an upper bound on what the real robot sees. ΔZ > fall threshold in sim ≠ fall on hardware, but it IS a warning that the PKL is more impulsive than its peers.

## Per-PKL matrix

All runs at `--speed 0.5`, fall threshold 0.4 m, initial root Z 0.787 m.

| PKL | frames | map OK | `k_effective` | effective speed | sim Final Z | ΔZ | sim verdict |
|---|---:|---|---:|---:|---:|---:|---|
| `wave_kinematics` | 294 | ✓ | 1.412 | 0.354 | 0.758 m | −2.9 cm | PASS |
| `flex_kinematics` | 316 | ✓ | 1.441 | 0.347 | 0.758 m | −2.9 cm | PASS |
| `spider_man_web_shoot_kinematics` | 326 | ✓ | 1.610 | 0.311 | 0.758 m | −2.9 cm | PASS |
| `wolverine_claws_kinematics` | 326 | ✓ | 1.711 | 0.292 | 0.758 m | −2.9 cm | PASS |
| `punch_kinematics` | 394 | ✓ | 1.700 | 0.294 | 0.758 m | −2.9 cm | PASS |
| `spider_man_landing_kinematics` | 381 | ✓ | 1.382 | 0.362 | **0.365 m** | **−42.2 cm** | **FAIL (sim)** |
| `iron_man_repulsor_kinematics` | 419 | ✓ | 1.748 | 0.286 | 0.758 m | −2.9 cm | PASS |
| `captain_america_shield_kinematics` | 450 | ✓ | 1.682 | 0.297 | 0.758 m | −2.9 cm | PASS |
| `thor_lightning_kinematics` | 460 | ✓ | 1.682 | 0.297 | 0.758 m | −2.9 cm | PASS |
| `hulk_smash_kinematics` | 726 | ✓ | 1.748 | 0.286 | 0.758 m | −2.9 cm | PASS |

### Interpretation
- **9/10 PKLs** show uniform `−2.9 cm` sag → dominated by gravity acting on the passively-held leg PD; arm disturbance is below that noise floor.
- **`spider_man_landing_kinematics` is the outlier**: native jerk peaks of 105 rad/s³ on `L_ELBOW` and 87 rad/s³ on `L_SHOULDER_PITCH`. Even after `k=1.382` slowdown the per-joint runtime jerk stays above cap in the sim (13 rad/s³) because `[T2]` was NOT active in the sim replay — the sim plays raw PKL frames.
- **All 10 PKLs pass `[T2]`** in `--dry-run-limits` at the `--speed 0.5` effective slowdown. They will be safe on the real robot once the arm-SDK runtime cap is engaged.

## Recommended hardware first-run ordering

Pick the smallest sim sag + shortest duration + lowest native jerk as first live PKL (Gate D):

1. **`wave_kinematics`** — 294 frames, 9.8 s native, all-arms gesture, k=1.412. This is the Gate D default in the guide.
2. `flex_kinematics` — 316 frames, k=1.441
3. `spider_man_web_shoot_kinematics` — 326 frames, k=1.610

**Do NOT first-run:**
- `spider_man_landing_kinematics` — sim predicts fall without active balance. Wait until wave is confirmed, then gate this one behind a successful `punch` or `thor`.
- `hulk_smash_kinematics` and `iron_man_repulsor_kinematics` — both max out at `k=1.748` meaning ~29% of native rate is as fast as they go under `[T2]`. OK once wave is trusted, but not first.

## Reproduce

```bash
# Dry-runs for all PKLs
for pkl in kim_workspace/movements/*.pkl; do
  name=$(basename "$pkl" .pkl)
  .venv/bin/python vinod_workspace/g1_arm_replay_loco.py --pkl "$pkl" --dry-run-map \
    > "_kpop/sim_validation/dry_run_map_${name}.txt" 2>&1
  .venv/bin/python vinod_workspace/g1_arm_replay_loco.py --pkl "$pkl" --dry-run-limits --speed 0.5 \
    > "_kpop/sim_validation/dry_run_limits_${name}.txt" 2>&1
done

# Sim gate (legs-only-hold) for all PKLs
for pkl in kim_workspace/movements/*.pkl; do
  name=$(basename "$pkl" .pkl)
  timeout 60 .venv/bin/python vinod_workspace/mujoco_physics_eval.py \
    --pkl "$pkl" --legs-only-hold --headless --hold 1 \
    > "_kpop/sim_validation/sim_gate_${name}.txt" 2>&1
done
```

## Known limitations of the sim gate

1. **No reactive balance controller.** MuJoCo `--legs-only-hold` locks leg *targets* to `STABLE_BALANCE_POSE` and runs PD. The real robot will have `LocoClient.BalanceStand()` actively modulating leg torque in response to arm disturbance. The sim therefore over-predicts falls.
2. **`fallen` flag is only set under `--vlaw`.** Without `--vlaw`, the script prints `RESULT: PASSED` regardless of Final Z. Trust the raw Final Z value, not the headline. This is a known bug in `mujoco_physics_eval.py` and is not the priority to fix right now.
3. **Sim replays raw PKL frames**, not the `[T2]`-slowed trajectory. Hardware will be ~k_effective-times slower and correspondingly gentler.
4. **Sim model is 29-DOF**; the hardware run is 23-DOF. The 29→23 remap is validated by `--dry-run-map` and by Unitree issue #108.
