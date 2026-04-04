# Kim's Workspace: RL & Simulation

This directory contains the necessary modules for Reinforcement Learning training via NVIDIA Isaac Lab, explicitly adapted for the Unitree G1 humanoid.

## Getting Started

1. Ensure your NVIDIA RTX GPU is configured.
2. Initialize the Isaac Lab Conda/uv environment.
3. Your core logic lives inside `rl_training/g1_rewards.py` (for custom PPO tracking) and `g1_randomization.py` (which includes 5 custom gap-closures: Action Delays, Hardware Torque Clipping, Damping, CoM shifts, and PD Gain fluctuations).

## VLAW Feedback Connection
*(Phase 3+)*
When your simulation agent flags a failure event, your `physical_logger.py` will communicate with Vinod's `server.py` to trigger an imitation-learning recovery pipeline.

**Do NOT push `hulk_smash_static.mp4` back to git, it will exceed limits.**
