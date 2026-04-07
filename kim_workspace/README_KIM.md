# Unitree G1 (23-DOF) Isaac Lab Training Suite

> **🚨 ATTENTION KIM: GLOBAL ARCHITECTURE HAS SHIFTED 🚨**
> The compute boundary has been radically redefined. You are now the sole owner of the entire VLAW GenAI extraction pipeline because the Mac cannot process it within latency bounds.
> **READ `VLAW_ARCHITECTURE_MEMO.md` IMMEDIATELY BEFORE PROCEEDING.**

> **For Kim (GPU Training Coordinator)**: This directory contains the configuration and foundational scripts needed to run a Sim-to-Real Reinforcement Learning (RL) training environment for the 23-DOF Unitree G1 robot in NVIDIA Isaac Lab. This policy ensures the robot doesn't fall over when tracking video-generated poses.

## Prerequisites
1. **Linux OS** (Ubuntu 22.04 recommended).
2. **NVIDIA GPU** (RTX 3090, 4090, or A100/H100) with proprietary NVIDIA drivers installed.
3. **NVIDIA Isaac Lab** installed.
4. **Unitree URDF/MJCF Assets**: You will need to drop the `unitree_robots/g1` folder containing the `g1_23dof.xml` meshes into Isaac Lab's asset directory.

## File Overview

*   `isaaclab_g1_env.py`: The wrapper setting up the robot in the Omniverse/Isaac engine. It registers the 23 joints and configures the Observation/Action spaces.
*   `g1_rewards.py`: Our custom PyTorch rewards. We aggressively penalize the robot for falling (root Z-height dropping below 0.4m) and reward it using an exponential kernel for perfectly matching our target poses.
*   `g1_randomization.py`: Crucial Sim-to-Real Domain Randomization. Randomizes the robot's physical mass and friction during training so the compiled neural network is robust to the real world.
*   `train.py`: The entry script. It launches thousands of clones of the G1 using the `rl_games` or `skrl` backend.

## How to Run

1. Open your terminal in the Isaac Lab Python environment.
2. Ensure you are running headless (to avoid rendering 4,000 graphical robots):
```bash
./isaaclab.sh -p kim_run/train.py --headless --num_envs 4096
```
3. Training to a stable static posture policy should converge in **~2 to 4 hours** on an RTX 4090.
4. Export the final model to `.onnx` and send it back to the Mac for real-time DDS deployment!
