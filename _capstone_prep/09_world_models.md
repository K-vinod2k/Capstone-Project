# Topic 9: World Models & Future Architecture

**What this section covers:** What world models are, how they fit into your pipeline, and how to answer "how would you improve this with NVIDIA Cosmos?"

---

## Section A — What Is a World Model?

**Q1. In one sentence, what is a world model?**
> A learned model that predicts `(state, action) → next_state` — it "imagines" what would happen next without actually running the robot, trained from video/sensor data instead of explicit physics equations.

**Q2. How is a world model different from MuJoCo simulation?**
> MuJoCo uses exact analytical physics equations — contact forces, rigid body dynamics. A world model is a neural network trained on data. MuJoCo gives full state access and runs fast but has a sim-to-real gap. World models are photorealistic, generalize across environments, but are slower and less precise. They are **complementary** — MuJoCo for control, world models for data augmentation and visual realism.

**Q3. Where does a world model fit in your pipeline right now? Where is the gap?**
> Your pipeline uses MuJoCo for physics eval (`mujoco_physics_eval.py`) and Isaac Lab for RL training. The gap: both are visually unrealistic simulations. The real robot looks different from simulation, which contributes to the sim-to-real gap. A world model (specifically Cosmos-Transfer) would bridge that gap by converting your MuJoCo renders to photorealistic video that the RL policy can train on.

---

## Section B — NVIDIA Cosmos Family

**Q4. What is Cosmos-Predict, and how could it help your project?**
> Cosmos-Predict is a video world model: text/image/video → future video. For your project, it could:
> - Generate synthetic training videos of hero poses in diverse environments (indoor, outdoor, crowded)
> - Validate whether a proposed joint trajectory looks physically plausible before committing to hardware
> **Limitation:** ~380 seconds per video on an H100 GPU — cannot be used in real-time control loops.

**Q5. What is Cosmos-Transfer, and where does it slot into your existing pipeline?**
> Cosmos-Transfer converts simulation renders (MuJoCo/Isaac Sim) → photorealistic video while preserving geometry via segmentation control. In your pipeline it would sit between `render_animations.py` and policy training:
> ```
> render_animations.py → MuJoCo video + segmentation mask
>     → Cosmos-Transfer
>     → photorealistic hero pose video
>     → RL training dataset (diverse environments)
> ```
> NVIDIA's result: +68.5% mission success on real hardware when training on Cosmos-Transfer outputs vs raw simulation renders.

**Q6. What is Cosmos-Reason1, and which module in your codebase could it replace?**
> Cosmos-Reason1 is a vision-language model (VLM) with chain-of-thought reasoning about physics and spatial feasibility. It could replace or augment `mujoco_physics_eval.py`:
> ```python
> # Current: ZMP/CoM check in MuJoCo (analytical)
> # Upgraded: visual feasibility check via VLM
> cosmos_reason1.chat("Is this robot pose stable? Reply FEASIBLE or INFEASIBLE")
> ```
> Advantage: can look at the actual rendered robot frame, not just joint angles — catches visual issues (arm collision with torso, weird wrist angle) that ZMP math misses.

**Q7. What is the difference between Cosmos-Reason1 and Cosmos-Predict?**
> Cosmos-Reason1 is a **reasoning model** (VLM) — it takes an image + text question and returns a text answer about physics feasibility, spatial relationships, or stability. Cosmos-Predict is a **generative model** — it takes context video/images and generates future video frames. Reason1 = judge/critic. Predict = dreamer/simulator.

---

## Section C — Latent World Models for Real-Time Control

**Q8. What is TD-MPC2 and how could it replace your open-loop PKL playback?**
> TD-MPC2 is a latent world model for real-time Model Predictive Control. It learns a compact latent space of the robot's dynamics and plans over it at ~1ms per step. Currently your system plays PKLs open-loop — if the robot drifts, it keeps playing the same trajectory regardless. TD-MPC2 would:
> - Replace the fixed PKL with a real-time planner
> - At each timestep, plan the best next action given the current encoder state
> - Adapt to disturbances (someone bumps the robot, floor is uneven)
> This would make hero poses **reactive** rather than pre-recorded.

**Q9. What is DreamerV3 and how does it relate to your Isaac Lab RL training?**
> DreamerV3 trains a policy entirely in **latent imagination** — it learns a world model from environment interactions, then imagines millions of rollouts in that latent space without querying the real simulator. Compared to your Isaac Lab PPO:
> - PPO: needs 4096 real Isaac Lab env steps → slow, GPU-intensive
> - DreamerV3: after initial data collection, trains actor-critic in latent space → much more sample efficient
> Could reduce RL training time significantly for hero pose tracking policies.

**Q10. Why can't you use Cosmos-Predict in your 500Hz control loop?**
> Cosmos-Predict takes ~380 seconds to generate one video on an H100 GPU. Your control loop runs at 500Hz — it needs a new action every 2ms. That's a 190,000× speed mismatch. World models like Cosmos-Predict are offline tools for data generation and evaluation, not online controllers. TD-MPC2 (~1ms/step) and DreamerV3 latent steps are the only world model variants fast enough for control loops.

---

## Section D — Integration Roadmap for Your Project

**Q11. What is the simplest world model integration you could demo in your project?**
> **Cosmos-Reason1 as a physics gate** — replace the `mujoco_physics_eval.py` ZMP check with a VLM call:
> 1. Render the first and peak frames of a new hero PKL using `render_animations.py`
> 2. Send frame + "Is this G1 robot pose stable for this hero move?" to Cosmos-Reason1
> 3. Use the FEASIBLE/INFEASIBLE response as the safety gate
> This is ~10 lines of code and directly upgrades an existing module.

**Q12. If you had Cosmos-Transfer running, how would you change the VLAW loop?**
> Current VLAW: crash → recovery PKL → imitation reward
> With Cosmos-Transfer:
> crash → recovery PKL → **render recovery video in MuJoCo** → **Cosmos-Transfer → photorealistic version** → policy trains on photorealistic recovery demonstration → better sim-to-real transfer of recovery behaviors
> The policy would see visually realistic crashes and recoveries, not just abstract joint trajectories.

**Q13. A judge asks: "Why not just use Cosmos to generate robot motions instead of your whole pipeline?" How do you answer?**
> Cosmos-Predict generates **video** of plausible future states — it cannot output robot joint angles directly. You still need the retargeting layer (GMR) to convert video → SMPL-X → G1 joint angles. Additionally, Cosmos doesn't know your robot's specific 23-DOF IDL joint limits, safety constraints, or hardware latency. Our pipeline is the layer that makes generated video executable on real hardware safely. World models and our pipeline are complementary, not alternatives.
