# Contributing to Capstone-Project

Thank you for your interest in contributing to the Unitree G1 Sim-to-Real Capstone Project! 

## Getting Started

1. **Fork the Repository**: Although we encourage direct collaboration via branching for direct maintainers, external contributors should fork this repository.
2. **Install Dependencies**: 
   - For `video2robot`, ensure you download the required SMPL-X models into `/video2robot/data` using the provided download scripts.
   - For `Mascot Unitree`, configure your python environment using `pip install -r requirements.txt` (or via `uv`).
   - For `kim_run`, you will need an active NVIDIA Isaac Lab installation and an RTX GPU.

## Submitting Pull Requests

1. **Create a Branch**: Create a descriptive branch (e.g., `feat/add-new-reward-function` or `fix/teleop-latency`).
2. **Review Code**: Ensure your physical torques are clipped dynamically before deploying to the Unitree SDK. We prioritize safety above all else.
3. **Draft the PR**: Open a new pull request and describe testing results. If submitting RL models from `kim_run`, please include a TensorBoard visual of the learning curve.
