# The "Lean" Architecture (Optimization Plan)

You are completely right. The original architecture is bloated and violates Occam's Razor for a 2-day sprint. The entire center block (Cosmos Video Generation + PromptHMR extraction + GMR retargeting) introduces 30 seconds of latency and massive failure risk. It is unnecessary if your strict goal is "feed inputs to the robot and watch it move."

Here is the proposed optimized architecture mathematically stripped of all non-essential compute layers.

## User Review Required

> [!WARNING]
> **What We Are Killing**
> To make this fast, real-time, and resilient, I propose we **terminate the Cosmos Video and PromptHMR pipelines entirely**. 
> - No more relying on generative MP4s.
> - No more offline `.pkl` extraction via two separate Python environments (`phmr` and `gmr`).
> - We reduce the system to just: **User Input $\rightarrow$ LLM Semantic Router $\rightarrow$ Direct Joint Angle Matrices $\rightarrow$ Robot.**

---

## The Optimized Structure

### 1. The Input Layer (Real-Time Control)
*Instead of slow generative AI interpreting text, we build a parametric controller.*
- **Hypothesis:** We can bypass video extraction completely by feeding LLM intents directly into a parameterized kinematic matrix.
- **The Execution:** You expand `hero_pose.py` into a dynamic interpolation engine. If the LLM says "Point at the ceiling", it doesn't wait for a video; it triggers the exact shoulder/elbow constraints in code.
- **The Gain:** Latency drops from 30,000ms to < 200ms.

### 2. The Sim-to-Real Bridge (Direct Actuation)
*The RL policy in Isaac Lab is still required to stabilize the G1 on the floor, but we can test inputs *open-loop* immediately using MuJoCo.*
- **Hypothesis:** For this 2-day sprint, the MuJoCo viewer (`mujoco_preview.py`) is perfectly sufficient as a hardware proxy for the 23-DOF humanoid.
- **The Execution:** You hook the input engine directly into MuJoCo. We stream `d_pos` targets directly to the `data.ctrl` array at 50Hz.
- **The Gain:** No real hardware needed at home. Instant visual validation of your input-to-action math.

---

## The Falsification Test (KPOP Loop)

**Claim:** A strictly programmatic, parameterized kinematic engine driven by an LLM router can safely and accurately animate the 23-DOF robot without requiring generative video.

**The Test:** 
1. You run `server.py` with the video backend disabled (`--no-video` flag).
2. You feed it 5 complex voice commands (e.g., "Ready your shield", "Wave with both hands").
3. We observe the immediate joint outputs traversing in MuJoCo.

If MuJoCo accurately mirrors the intent without crashing or causing self-collision, we have mathematically proven the massive Video/HMR pipeline is an unnecessary step.

### Do we agree on stripping out the Cosmos/PromptHMR layers for this sprint?
