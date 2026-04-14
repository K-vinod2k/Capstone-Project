# Topic 6: RL Training, Sim-to-Real & VLAW Loop

**What this section covers:** Isaac Lab PPO training, domain randomization, and the crash-recovery feedback loop.

---

## Section A — RL Training Setup

**Q1. What framework is used for RL training, and what does it require to run?**
> Isaac Lab (NVIDIA's robotics RL framework built on Isaac Sim). Requires: Linux OS, NVIDIA GPU (RTX-class recommended), Isaac Lab Python environment, and the G1 URDF/MJCF assets. Training runs on Kim's Linux GPU machine.

**Q2. How many parallel environments are used during training? Why so many?**
> 4096 parallel environments (`--num_envs 4096`). RL needs millions of environment steps to learn stable locomotion — 4096 envs running simultaneously dramatically accelerates wall-clock time. Each env runs independently with different domain randomization parameters, so the policy sees diverse physics conditions simultaneously.

**Q3. What algorithm is trained — what is PPO and why is it suitable for locomotion?**
> PPO (Proximal Policy Optimization). Suitable for locomotion because: (a) on-policy — uses fresh experience, important for contact-rich dynamics, (b) clipping prevents catastrophically large policy updates that could destabilize training, (c) handles continuous action spaces (joint angles) natively, (d) empirically stable on humanoid locomotion benchmarks.

**Q4. What is the reward function trying to maximize? What does "pose tracking" mean as a reward?**
> The reward maximizes pose tracking (how closely the robot's joints match the target PKL trajectory) minus fall penalty. Pose tracking reward = `exp(-α × ||q_current − q_target||²)` — exponential kernel so reward is high when close, decays sharply when far. The policy learns to follow the hero animation trajectory without falling.

**Q5. What is the fall penalty, and at what height does it trigger?**
> Fall penalty = **-100** applied when `root_Z < 0.4m` (robot's pelvis drops below 40cm — indicates a fall). This is a hard negative reward that discourages any behavior leading to the robot toppling.

---

## Section B — Domain Randomization

**Q6. What is domain randomization, and why is it critical for sim-to-real transfer?**
> Domain randomization randomly varies physical simulation parameters (mass, friction, motor gains) across environments during training. Forces the policy to be robust to parameter uncertainty. Critical because: the real robot's exact physics (joint friction, motor delay, center of mass) will never perfectly match the simulation — a policy trained on one exact physics setting often fails on real hardware.

**Q7. Which physical parameters are randomized in g1_randomization.py?**
> Body mass, joint friction, motor gain variations, ground friction coefficients, and external force perturbations. These cover the most common sources of sim-to-real gap.

**Q8. If you skip domain randomization, what happens when you deploy to the real robot?**
> The policy overfits to the simulation's exact physics. On the real robot, slightly different friction or mass distribution causes the policy to take wrong corrective actions — typically resulting in falls within the first few steps. This is called "reality gap collapse."

**Q9. What is the sim-to-real gap? Give one concrete example from your project.**
> The sim-to-real gap is the difference between simulated and real-world physics. Concrete example from this project: DDS domain mismatch — simulation used domain 1, real hardware uses domain 0. Early deployment scripts had `ChannelFactoryInitialize(1, ...)` which worked in sim but sent commands on the wrong DDS domain on real hardware — the robot received nothing. Fixed by making domain a `--domain` argument defaulting to 0.

---

## Section C — The VLAW Loop

**Q10. What does VLAW stand for conceptually? What problem does it address?**
> VLAW = **V**irtual-to-Real **L**earning **A**daptation **W**orkflow (conceptually). It addresses the problem that RL training in simulation doesn't automatically improve when the policy fails in specific ways — VLAW creates a closed feedback loop where real-world-style failures (detected in simulation) are converted to recovery demonstrations that are fed back into training.

**Q11. Walk through the VLAW feedback cycle step by step: crash → ... → improved policy.**
> 1. Isaac Lab simulation detects fall: `root_Z < 0.4m`
> 2. `sim_logger.py` captures crash state and POSTs telemetry to `server.py /vlaw_sim_sync`
> 3. `server.py` returns a recovery PKL path (nearest stable animation to the crash state)
> 4. `vlaw_orchestrator.py` loads recovery PKL and injects it as imitation learning reward for next episode
> 5. PPO trains on both standard RL reward AND imitation reward from recovery demonstration
> 6. Policy learns the recovery trajectory, reducing crashes in that failure mode
> 7. Loop continues — new crash modes trigger new recovery demonstrations

**Q12. What does sim_logger.py detect, and what does it send to the server?**
> Detects: ZMP collapse (center of pressure outside support polygon) OR root height < 0.4m. Sends: crash state dict including current joint positions, velocity, root pose, and episode step number. This telemetry helps the server select the most appropriate recovery animation.

**Q13. What does vinod_workspace/server.py do? What endpoint does it expose?**
> A minimal FastAPI server running on port 8080. Exposes `/vlaw_sim_sync` (POST) — receives crash telemetry, looks up the nearest stable recovery PKL from the movements library, and returns the PKL path as JSON. It's the bridge between Kim's simulation machine and Vinod's motion library.

**Q14. How does a recovery PKL become imitation learning data for the next training run?**
> `vlaw_orchestrator.py` loads the recovery PKL's joint trajectories and computes an additional reward signal: how closely the current policy's output matches the recovery trajectory. This imitation reward is added to the PPO objective, nudging the policy toward the recovery motion when in a fall-prone state.

**Q15. What is the stopping condition — when does the VLAW loop terminate?**
> When the policy achieves a target success rate (episode completion without fall) across evaluation environments, or when the crash rate drops below a threshold. In practice, training is also bounded by compute budget (number of env steps).
