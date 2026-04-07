# Cross-Team Architecture Pivot: VLAW Compute Resources

**To:** Kim (RL Training / Linux Cluster Lead)
**From:** Vinod (Mac OS / UI & Architecture)
**Subject:** Moving ALL GPU workloads to your domain for VLAW Integration

Kim, we have completely verified the baseline 23-DOF physics tracking mathematically on the Mac via `mujoco_physics_eval.py`. We have also stripped `server.py` of all its heavy CUDA dependencies. 

Because the Mac running local LLM/VLM processing is fundamentally bottlenecked (CPU inference takes ~30 mins per video frame), we are implementing a **hard architectural Compute Boundary**.

## The Compute Boundary Redraw
1. **The Mac Ecosystem (Vinod):** Handles ONLY deterministic logic -> Safe PD array validation, Network routing, UDP Hardware bridging, and UI fallback endpoints.
2. **The Linux Ecosystem (Kim):** You are now the sole owner of the entire generative VLAW feedback loop.

## What You Must Build for the VLAW Loop

Because the VLAW RL training cycle requires thousands of rapid recoveries, the entire loop must now run natively alongside Isaac Lab on your Linux GPU cluster. 

Here is exactly how the loop executes entirely inside `kim_workspace`:

### Step 1: The Crash Trigger & Hallucination
Inside `sim_logger.py` or your `train.py` loop: When the RL agent drops the G1 Z-height below 0.4 meters, it means the robot has fallen. Your script must immediately pause the Isaac Lab simulation, hit the local VLM or Cosmos API *natively from your Linux box* to hallucinate the recovery sequence.

### Step 2: Trajectory Extraction (`headless_extraction.py`)
Because you have A100s/RTX4090s, the `headless_extraction.py` (PromptHMR pipeline) now lives in your domain. Your Isaac Lab wrapper must automatically pass the hallucinated video to this script, allowing your GPU to extract the `.pkl` 23-DOF array in seconds instead of minutes.

### Step 3: Imitation Learning (`g1_rewards.py`)
This remains your most critical task. Your Isaac Lab environment receives the `recovery.pkl` locally. Instead of ending the episode, your RL agent resets to the fallen state, ingests the `.pkl`, and targets its Imitation Reward function specifically to copy that `.pkl` arrays trajectory. Over thousands of attempts, the policy learns to stand back up.

## The Physical Constraints (The Standard)
The standard you must adhere to: 
When your RL agent executes the simulation step, you must enforce an integration timestep (`dt`) of `0.002` or lower. If you use the default 0.005, the impact forces of hitting the ground will cause the Isaac physics engine to mathematically explode. 

Once your `.onnx` output from this loop proves stable, push it. We will pull it onto the Mac and pass it down to the physical Unitree hardware over DDS.
