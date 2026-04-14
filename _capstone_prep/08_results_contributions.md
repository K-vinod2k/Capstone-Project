# Topic 8: Results, Contributions & Future Work

**What this section covers:** What you actually demonstrated, what is novel, and what comes next.

---

## Section A — Results

**Q1. How many hero animations did you implement? Name them all.**
> 10 animations:
> 1. `wave` — friendly greeting
> 2. `flex` — muscle flex pose
> 3. `punch` — forward punch
> 4. `hulk_smash` — both arms overhead slam
> 5. `iron_man_repulsor` — repulsor blast, arm extended
> 6. `spider_man_web_shoot` — web-shooting gesture
> 7. `spider_man_landing` — superhero landing crouch
> 8. `captain_america_shield` — shield throw pose
> 9. `thor_lightning` — arms raised, lightning summon
> 10. `wolverine_claws` — claws-out aggressive stance

**Q2. Which animation worked best on hardware, and what made it successful?**
> `wave` was the first to work cleanly on hardware — simple single-arm motion, low joint velocities, minimal balance demands. `wolverine_claws` (87 frames) also ran cleanly with mode_machine=4 captured, all frames completing and clean disengage.

**Q3. What was the hardest animation to get working, and why?**
> `hulk_smash` — requires both arms moving symmetrically. Required debugging: (a) IDL joint index confusion (23-DOF vs 29-DOF), (b) right shoulder roll sign convention causing right arm to press inward instead of extending outward, (c) PKL format mismatch after incorrect remap_23dof.py application.

**Q4. What was the first visible sign that the hardware deployment was working?**
> The wave animation playing on real hardware with the DDS output showing `mode_machine=4` captured, 121 frames completing, and the robot's arm visibly raising and waving before the clean disengage. This confirmed: DDS connected, mode_machine correct, MotionSwitcherClient released, velocity clamp holding.

**Q5. Describe one specific bug you found and fixed during hardware testing.**
> **mode_machine mismatch:** The robot reports its current operational mode in LowState as `mode_machine=4`. Our deploy_real.py originally hardcoded `mode_machine=0` in every LowCmd. The robot silently discarded every command — no error, no feedback, robot didn't move. Fix: on first LowState message, read `msg.mode_machine` and echo it in every subsequent LowCmd. Documented in KPOP log H6.

---

## Section B — Novelty & Contributions

**Q6. What is the most technically novel part of your project? Why hasn't this been done before?**
> The end-to-end pipeline from free-form natural language → video synthesis → human pose extraction → robot retargeting → real hardware execution, with an automated safety validation layer and sim-to-real feedback loop. Prior work either stops at simulation, requires manual motion capture, or uses pre-scripted animations. We combine all stages into a single automated pipeline.

**Q7. How is your approach different from motion capture + replay on a robot?**
> Motion capture requires a physical actor in a mocap suit, expensive equipment, and produces actor-specific data. Our pipeline: (a) generates motion from text prompts — no physical actor needed, (b) uses video generation to create novel motions on demand, (c) automatically retargets to the robot's specific DOF structure, (d) validates safety before deployment. Mocap can't generate new motions from "be Iron Man" at runtime.

**Q8. What does the VLAW loop contribute that standard RL training does not?**
> Standard RL: the policy learns from reward signals alone; failures are just negative rewards. VLAW: failures trigger the generation of recovery demonstrations (from the motion library) that the policy can imitate. This converts failure modes into structured learning signals — the policy doesn't just learn "falling is bad," it learns "when in this state, do this recovery motion." Faster convergence on fall recovery than reward shaping alone.

**Q9. Your system uses KPOP (Karl Popper) debugging methodology. What is it and why did you adopt it?**
> KPOP: for every bug, form one falsifiable hypothesis, predict a measurable outcome, run the minimal test, record the result as FALSIFIED or NOT FALSIFIED. Adopted because hardware debugging is expensive — you can't run 1000 random tests on a real robot. KPOP forces you to think before you act: each test is purposeful, the log captures what was ruled out, and the team doesn't repeat the same failed hypothesis. Produced 8 experiment logs in `_kpop/`.

**Q10. If someone wanted to add a new hero (e.g., Batman), what would they need to do? How long would it take?**
> 1. Write a text prompt describing Batman's signature move (e.g., "Batman throws a batarang with cape sweep")
> 2. Run `video2robot/scripts/run_pipeline.py --action "..."` to generate the PKL (~3-5 min)
> 3. Add entry to HERO_REGISTRY in `persona_brain.py` with Batman's keywords and persona
> 4. Add reply to REPLIES dict in `example.py`
> 5. Run `generate_rag_dataset.py` to update the FAISS index
> Total time: ~30 minutes of human effort + pipeline runtime.

---

## Section C — Limitations & Future Work

**Q11. What are the two biggest limitations of the current system?**
> 1. **Pre-computed animations only** — the system can only perform the 10 pre-built hero animations. It cannot generate a novel motion at runtime in response to a completely new request.
> 2. **No balance adaptation** — trajectories are played open-loop; if the robot starts slightly off-balance, it executes the animation without corrective adjustment. The RL policy isn't yet integrated into the live deployment path.

**Q12. The video-to-robot pipeline produces motion from a single video viewpoint. What problems does this cause?**
> Monocular depth ambiguity: PromptHMR infers 3D body pose from a single camera angle. Depth information is estimated, not measured. This causes: (a) flipped limbs (the model can't always tell if an arm is in front of or behind the body), (b) scale errors (wrong distances between joints), (c) artifacts for non-frontal views where limbs overlap.

**Q13. What would it take to make the robot respond in real-time to user movements?**
> Real-time teleoperation would require: (a) live human pose estimation at 30+ FPS (e.g., from a webcam with MediaPipe or PromptHMR streaming), (b) online retargeting of each frame in <33ms, (c) streaming joint angles to deploy_real.py instead of loading a PKL, (d) a real-time safety filter (velocity check per frame), (e) latency under ~100ms for responsive feel. This is feasible but would require significant re-engineering of the pipeline.

**Q14. What would you change in the architecture if you had 6 more months?**
> 1. Integrate the RL policy into the live deployment path for balance-aware execution
> 2. Real-time video streaming → live pose → live robot (remove pre-computation requirement)
> 3. Multi-turn conversation memory in the persona engine (robot remembers previous interactions)
> 4. Bilateral arm sign convention fix in remap_23dof.py and validated across all 10 animations
> 5. Web UI for non-technical operators to trigger animations from a tablet

**Q15. What would make this system ready for a public demo at a trade show?**
> 1. Fully working bilateral arm motion (both arms symmetric) — currently right arm roll sign being debugged
> 2. Gantry or safety barrier to protect the robot and public
> 3. Voice input working reliably in noisy environments (better STT with noise cancellation)
> 4. Graceful failure recovery — if DDS drops, robot goes to safe damping mode automatically
> 5. Pre-tested battery of prompts that reliably map to the best-performing animations
