# Phase 4: Imitation Retargeting & RL Co-Training

**Goal:** Process the static Hulk video through the PromptHMR pipeline to extract its 35-DOF kinematics, and retrain Kim's Isaac Lab RL policy to imitate those recovery kinematics whenever the simulation falters.

## To-Do List

- [ ] **4.1. Headless Pose Extraction:** Feed `hulk_smash_static.mp4` through Vinod's `video2robot/third_party/PromptHMR` pipeline. Execute this entirely headless (no UI) to produce `hulk_kinematics.pkl`.
- [ ] **4.2. Verify Kinematics:** Read `hulk_kinematics.pkl` and map the SMPL-X format explicitly to the Unitree G1's 35 joint indexes (ensuring no physically impossible torques are represented in the simulation).
- [ ] **4.3. Inject Imitation Reward:** Modify Kim's `g1_rewards.py` within the `rl_training/` folder. Add a reward tracking term: `def imitation_recovery_reward()`. This should calculate the L2 distance between the simulated robot's current pose and the nearest keyframe in `hulk_kinematics.pkl`.
- [ ] **4.4. Write VLAW Orchestrator:** Create `kim_workspace/rl_training/vlaw_orchestrator.py`. This script will wrap the Isaac Lab environment, run episodes until failure, call Vinod's handshake API, load the updated `.pkl`, and continuously re-train the PPO policy.
- [ ] **4.5. Phase 4 Checkpoint Log:** Commit the Retargeting Loop.
  - `git add . && git commit -m "feat(phase4): launch closed-loop vlaw imitation RL training"`
