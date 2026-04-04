# Phase 1: Clean Architectural Separation & Sim-Focus

**Goal:** Establish perfect isolation between Vinod's Generative AI pipeline and Kim's Reinforcement Learning pipeline, while shifting the entire project's focus natively toward simulation-first testing (ignoring delayed hardware testing for now).

## To-Do List

- [ ] **1.1. Core Server Relocation:** Move `server.py`, `persona_brain.py`, and `hf_video_client.py` from `Mascot Unitree/` directly into `vinod_workspace/Phase_1/` or its root to isolate Vinod's logic.
- [ ] **1.2. Purge Old Directories:** Safely delete the now-empty `Mascot Unitree/` directory and `Unitree_G1_Teleop_Test/` directory (since their contents were moved).
- [ ] **1.3. Clean Root Repository:** Archive or delete `CLAUDE.md`, `_kpop/`, and other loose experiment logs so the root repo contains *only* `vinod_workspace/`, `kim_workspace/`, the READMEs, and the core repo config files.
- [ ] **1.4. Update Gitignore:** Ensure Phase 1 logs and checkpoints do not accidentally push large local files.
- [ ] **1.5. Kim's Simulation Verification:** Verify `kim_workspace/rl_training/g1_randomization.py` and `g1_rewards.py` are strictly configured for Isaac Lab headless training on RTX GPUs, with no hardcoded local paths that would break on Kim's machine.
- [ ] **1.6. Create Kim's README:** Create `kim_workspace/README_KIM.md` outlining the exact pip/conda commands Kim needs to run the Isaac Lab simulation.
- [ ] **1.7. Phase 1 Checkpoint Log:** Commit all Phase 1 restructuring to Git.
  - `git add . && git commit -m "feat(phase1): isolate vinod and kim workspaces for simulation"`
