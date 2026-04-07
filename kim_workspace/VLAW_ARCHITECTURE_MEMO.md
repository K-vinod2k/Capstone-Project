# VLAW GPU Architecture Pivot

Hey Kim, we figured out the compute split for the VLAW loop.
Since running the video generation and PromptHMR takes like 30 minutes on my Mac CPU, we're shifting all the heavy GPU jobs to your Linux environment.

## The New Plan
My Mac is just going to handle the UI routing and final physics testing. Your Linux machine will handle the entire VLAW imitation-learning loop.

Here is how the loop should work on your end:

**1. Crash Trigger:** When the robot falls over in Isaac Lab (Z-height drops below 0.4), your script (`sim_logger.py` or similar) pauses and triggers the GenAI video generation native on your machine.
**2. Trajectory Extraction:** Because you have the CUDA cores, you'll run `headless_extraction.py` (the PromptHMR pipeline) to process the video and extract the `.pkl` data in seconds.
**3. RL Training:** Your Isaac Lab imports the `recovery.pkl` and uses imitation learning (`g1_rewards.py`) so the agent learns to mimic the recovery and stand back up.

## Physics Note
I've already tested the `g1_23dof.xml` math constraints on my macOS using a hard physics evaluator. One important thing: make sure your Isaac Lab simulation timestep (`dt`) is set to `0.002` or lower, otherwise the physics engine will literally explode when the robot hits the ground. 

Let me know once you get the Isaac loop running!
