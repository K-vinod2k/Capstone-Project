# Unitree G1 Mascot: Video-to-Humanoid Capstone

Welcome to the central repository for the Unitree G1 Capstone Project. This monolithic repository contains the full end-to-end pipeline required to translate natural language and video inputs into physical humanoid movements.

## Directory Structure

* **`video2robot/`**: The core foundational pipeline to ingest text/video, retarget human pose kinematics mathematically, and output `.pkl` action trajectories using PromptHMR and GMR logic.
* **`Mascot Unitree/`**: The central orchestration layer. Includes testing scripts, physical deployment layers (`deploy_real.py`), the UI React interface, and superhero persona constraints (`persona_brain.py`) that formulate the initial generative inputs.
* **`Mascot Unitree/kim_run/`**: The dedicated NVIDIA Isaac Lab Reinforcement Learning (RL) training environment. This is specifically used to take pose targets and distill them into safe, gravity-aware Whole-Body Control torques via Domain Randomization to prevent the robot from falling over.
* **`Unitree_G1_Teleop_Test/`**: Reference specs and basic physical teleoperation configurations directly aligned with the hardware's 23-DOF and 35 motor DDS layout. 

## Workflow Summary
1. **Pose Generation**: The system listens to a user, generates an inference via superhero personas, and produces a reference video.
2. **Retargeting**: `video2robot` extracts spatial 3D human meshes from the video and calculates approximate joint angles.
3. **Sim-to-Real RL Filtering (Isaac Lab)**: The generated joint angles are passed to a trained neural network which outputs physically-safe, balanced torques.
4. **Physical Deployment**: Safe vectors are continuously published over CycloneDDS to the Unitree G1 hardware.

## How to use
To work on the RL side of the pipeline (GPU required), navigate directly to `/Mascot Unitree/kim_run/` and review the specific README inside that folder!
