# Session Log — 2026-04-20

## Summary
Two main threads: (1) PKL simulation debugging, (2) G1 internal stabilization SDK discovery.

---

## 1. PKL Simulation — `2026-03-12_07-07-09.pkl`

**File:** `Pkl files/2026-03-12_07-07-09.pkl`
- Format: `dof_pos` shape (1589, 29), fps=30.0 — raw GMR/PromptHMR output
- MuJoCo model (`scene.xml`) has nu=29 actuators, matching this shape

**Fix applied — `vinod_workspace/mujoco_physics_eval.py`:**
- Added FPS-aware downsampling: reads `fps` key from PKL, downsamples to `ANIMATION_FPS=10` by stepping every `round(pkl_fps / ANIMATION_FPS)` frames
- Before fix: 1589 frames played at 1/3 speed (3× too slow)
- After fix: downsamples to 530 frames, correct 10fps timing

**Simulation result with `--hold 2`:**
- HOLD phase: stable, Z=0.758m, pitch~-2.8° ✓
- PKL_TRANSITION: pitch rises to +18.8° — leg joint mismatch detected
- PKL_PLAYBACK: pitch +52°, Z drops to ~0.37m — robot falls

**Root cause:** G1 PKL leg values (knee≈0, hip_pitch≈+0.11) don't match MuJoCo standing convention (knee=+0.6, hip_pitch=-0.3). The real hardware uses Unitree's locomotion controller for balance while arms do hero gestures — the PKL leg DOF are not meant to be replayed in a standalone physics sim.

**Recommended fix:** Run with `--legs-only-hold` flag to lock DOF 0–14 to `STABLE_BALANCE_POSE` and only stream arm joints (DOF 15–28) from the PKL. Command:
```bash
.venv/bin/mjpython vinod_workspace/mujoco_physics_eval.py \
  --pkl "Pkl files/2026-03-12_07-07-09.pkl" \
  --hold 2 --legs-only-hold
```

---

## 2. G1 Internal Stabilization SDK Discovery

**Finding:** The G1 has a built-in stabilization algorithm on the locomotion computer (`192.168.123.161`), accessible via `LocoClient` in `unitree_sdk2_python`.

**Repo:** https://github.com/unitreerobotics/unitree_sdk2_python

**Key SDK module:** `unitree_sdk2py.g1.loco.g1_loco_client.LocoClient`

**Known methods:**
- `Damp()` — damping/safe mode
- `Start()` — stand up (FSM 200)
- `Move(vx, vy, vyaw, continuous)` — velocity walk command
- `StopMove()` — stop walking
- `BalanceStand()` — balance in place
- `ROBOT_API_ID_LOCO_SET_ARM_TASK` — arm task API (commands arm joints while loco holds balance)

**Critical insight:** `LOCO_SET_ARM_TASK` solves the open research question in CLAUDE.md — you CAN do simultaneous balance + arm control without releasing motion mode. This is the path to hero gestures while the robot walks/stands.

**SDK not currently installed in venv.** Install on Linux GPU machine (Kim's):
```bash
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
cd unitree_sdk2_python
pip install -e .
```

**Next step:** Investigate `SetArm()` / arm task API signature and integrate into `g1_arm_replay_airborne.py` as an alternative to full low-level takeover.

---

---

## 3. LeRobot + Locomotion Controller Research

**Repo:** https://github.com/huggingface/lerobot

### LeRobot G1 Integration
- Full native G1 driver at `src/lerobot/robots/unitree_g1/`
- Targets **29-DOF** (with wrists); our hardware is 23-DOF — arm index starts at 15 in LeRobot vs 13 in our IDL. PKLs are **not interchangeable** without remapping.
- "Both 29 and 23 DoF variants are supported" in docs is misleading — no 23-DOF-specific code exists; wrist commands just silently no-op on 23-DOF hardware.
- Their `disconnect()` sends zero-gain command before stopping (our known ease-out gap — should add this to `deploy_real.py`).
- **Simultaneous balance + arm control solved** via background controller thread: controller thread owns joints 0–14 (legs + waist) at its own Hz; main loop publishes arm targets on top. This is the clean answer to our open research question.
- ZMQ bridge (`run_g1_server.py` on Jetson, `unitree_sdk2_socket.py` on client) serializes DDS over JSON+base64 on ports 6000/6001 — more robust than our current approach.
- Gravity compensation via Pinocchio + CasADi (`G1_29_ArmIK.solve_tau()`) available if arm sag is a problem.

### GrootLocomotionController (NVIDIA SONIC)
- **Paper:** *"SONIC: Supersizing Motion Tracking for Natural Humanoid Whole-Body Control"* — arXiv:2511.07820
- **Architecture:** `UniversalTokenModule` (ATM) — multiple MLP encoders (`[2048, 1024, 512, 512]`, SiLU) → FSQ bottleneck (32 levels, 2 tokens) → decoder → joint targets
- **Multi-modal inputs:** G1 native, SMPL mocap, VR teleop — all share the same FSQ token space
- **Training:** PPO on Isaac Lab, 142K+ human motions (BONES-SEED dataset, ~288 hours), 64+ GPUs for finetuning
- **Input:** 516D = 6-frame history × 86D/frame (temporal context)
- **Inference rate:** 50 Hz; two ONNX policies — Balance (when `||cmd|| < 0.05`) + Walk
- **Deployed as:** `GR00T-WholeBodyControl-Balance.onnx` + `GR00T-WholeBodyControl-Walk.onnx` from `nepyope/GR00T-WholeBodyControl_g1` on HF Hub
- **Weakness for our use:** No arm-masking — large hero pose arm movements could perturb balance estimate

### HolosomaLocomotionController (Amazon FAR)
- **Authors:** Amazon FAR, Pieter Abbeel, Alejandro Escontrela, Angjoo Kanazawa, Karen Liu, Carlo Sferrazza, Guanya Shi, Brent Yi et al.
- **Algorithm:** FastSAC (fast Soft Actor-Critic, off-policy) or PPO (selectable)
- **Architecture:** Simple 3-layer shrinking MLP — `hidden → hidden//2 → hidden//4`, LayerNorm + SiLU, Gaussian policy head (fc_mu + fc_logstd)
- **Input:** 100D flat observation — `[last_action(29), ang_vel(3), cmd_yaw(1), cmd_xy(2), cos_phase(2), qj(29), dqj(29), gravity(3), sin_phase(2)]`
- **Gait phase clock:** Explicit sin/cos oscillator (0.5s period) fed as observation — freezes at π when standing, restarts on movement
- **Key advantage:** **Arm-masking** — feeds `DEFAULT_ANGLES` for arm joints into policy obs instead of actual encoders, so hero poses never destabilize the balance network
- **KP/KD embedded in ONNX metadata** — extracted at load, no separate tuning
- **Inference rate:** 200 Hz (`CONTROL_DT=0.005`) — 4× faster than GR00T
- **Deployed as:** `fastsac_g1_29dof.onnx` from `nepyope/holosoma_locomotion` on HF Hub
- **Best fit for our project:** Lighter, faster, arm-masking means hero poses won't destabilize legs

### Recommendation
For integrating a balance controller into our pipeline, **Holosoma FastSAC is the better drop-in**:
- 200 Hz, simple MLP, arm-masking decouples arm motion from balance
- KP/KD baked into ONNX — no gain tuning
- Only blocker: 29-DOF joint index offset (their arms at 15, ours at 13) needs remapping

---

## Files Changed This Session
- `vinod_workspace/mujoco_physics_eval.py` — FPS downsampling fix for PKL playback

## Open Items
- ~~Run `--legs-only-hold` sim to validate arm motion from PKL~~ — **CLOSED 2026-04-20**: ran on all 10 PKLs in `kim_workspace/movements/`; 9/10 pass with 2.9 cm passive sag, `spider_man_landing` outlier (Final Z 0.365 m). Matrix + raw logs: `_kpop/sim_validation/`.
- ~~Get full `LocoClient.SetArm()` signature from SDK repo~~ — **MOOT**: the actual supported coexistence API is `rt/arm_sdk` + `motor_cmd[29].q` weight bit (Unitree issue #108). `SetArm()` was a wrong trail; `LocoClient` is not mixed with arm-SDK at all.
- ~~Integrate `LocoClient` arm task into deployment pipeline~~ — **CLOSED 2026-04-20**: `vinod_workspace/g1_arm_replay_loco.py` implements the `rt/arm_sdk` path with engage ramp, `[T2]` loco-aware velocity/jerk limiter, cubic Hermite playback, ease-out, and `--jog-test` / `--engage-only` pre-flight gates. Operator guide: `kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md`. Hardware gate orchestrator: `iotlab_gate_runner.sh`.

## Hardware gate status (pending)
- Gate A (DDS readback) — not yet run on iotlab.
- Gate B (single-joint jog, idx 15 / 22 / 19) — not yet run on iotlab.
- Gate C (engage-only, weight 0 → 0.1 → 0) — not yet run on iotlab.
- Gate D (wave PKL playback at `--speed 0.5`) — not yet run on iotlab.
