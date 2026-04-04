# Phase 3: Simulated VLAW Feedback Loop

**Goal:** Establish the bridge between Kim's Isaac Lab RL Simulation and Vinod's pose extraction pipeline using a Simulated Failure Logger, fully mapping the "Iterative Co-improvement" (VLAW) physics to our simulation environment instead of physical hardware.

## To-Do List

- [ ] **3.1. Build Simulated Failure Logger:** Write `kim_workspace/rl_training/sim_logger.py`. Instead of reading a physical robot SDK, this script will hook into Isaac Lab's episode termination events (e.g., when the simulator flags `base_height < 0.4` or `pitch > 0.5`).
- [ ] **3.2. Record Simulation State:** When a failure triggers, dump the last 50 frames of Isaac Lab joint telemetry into a JSON file (`latest_sim_failure.json`).
- [ ] **3.3. Build Internal Handshake API:** Create an endpoint in Vinod's `server.py` named `/vlaw_sim_sync`. Kim's logger will POST the `latest_sim_failure.json` to this endpoint.
- [ ] **3.4. Trigger Hulk Recovery:** When Vinod's server receives a simulation failure, it recognizes the robot has fallen. The server will pull the static `hulk_smash_static.mp4` video (from Phase 2) as the designated "recovery/aggressive motion" template.
- [ ] **3.5. Phase 3 Checkpoint Log:** Commit the handshake API and simulated logger to Git.
  - `git add . && git commit -m "feat(phase3): establish sim-to-ai vlaw handshake protocol"`
