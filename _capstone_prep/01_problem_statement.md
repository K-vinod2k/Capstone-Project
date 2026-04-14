# Topic 1: Problem Statement & Motivation

**What this section covers:** Why the project exists, what gap it fills, and how you pitch it to a non-technical audience.

---

## Section A — The Core Problem

**Q1. In one sentence, what problem does your project solve? (No jargon.)**
> You type or say something like "do Iron Man" and a humanoid robot performs that superhero move — our system bridges the gap between natural language and physical robot motion.

**Q2. Why is it hard to make a robot perform expressive, human-like motion from a voice command?**
> Four separate hard problems must be solved in sequence: (1) understanding intent from free-form language (LLM), (2) generating plausible human body motion for that intent (video gen + pose estimation), (3) retargeting human motion to a robot's different joint structure (GMR), and (4) deploying it safely without the robot falling or breaking joints (physics eval + PD control). Each step has its own failure modes.

**Q3. What existed before your project? What was missing?**
> Pre-scripted robot motion libraries existed, but they required manual animation. Text-to-robot motion pipelines did not exist end-to-end. What was missing: (a) natural language → robot motion, (b) automatic safety validation before hardware, (c) a closed-loop recovery system (VLAW) that learns from failures.

**Q4. Who is the end user? What do they want to type or say, and what do they want the robot to do?**
> A person at an event, trade show, or museum. They say something casual like "hulk smash" or "be Spider-Man" and expect the robot to respond with the correct character's signature move and a matching quote — no technical knowledge required.

---

## Section B — Why Humanoid Robots

**Q5. Why use a humanoid robot specifically, rather than a robotic arm or drone?**
> Humanoid robots have the same body structure as the heroes being imitated — two arms, a torso, upright stance. A robotic arm can't do a "Hulk Smash" pose. Humanoid form makes the performance visually recognizable and emotionally resonant to a human audience.

**Q6. What makes the Unitree G1 a good platform for this project?**
> The G1 is commercially available, has 23 active DOF covering legs + torso + arms, comes with an open SDK (unitree_sdk2py) with DDS-based low-level control, and has an active developer community. It's agile enough for dynamic poses but stable enough for lab testing.

**Q7. What is the difference between a 23-DOF and 29-DOF G1, and why does it matter for your work?**
> The 29-DOF model adds waist roll/pitch (joints 13-14) and wrist pitch/yaw on each arm (joints 20-21, 27-28). The 23-DOF model omits these — waist is fixed and arms end at wrist roll. This matters because the hardware IDL index layout is different: on 23-DOF, arm joints start at index 13; on 29-DOF they start at index 15. Sending commands to the wrong indices causes wrong joints to move or nothing to move at all.

---

## Section C — Why This Is Non-Trivial

**Q8. What are the three biggest technical challenges between "user says Iron Man" and "robot does Iron Man"?**
> 1. **Intent resolution** — "Iron Man" must map to the repulsor-blast animation, not just any pose. Done via FAISS RAG semantic search.
> 2. **Motion retargeting** — Human SMPL-X body has different proportions and DOF than the G1. GMR converts between them.
> 3. **Hardware safety** — A joint commanded to move 2.5 rad too fast will strip gears. Velocity clamping, physics eval, and ease-in prevent this.

**Q9. Why can't you just look up a pre-made motion clip and play it directly?**
> Two reasons: (a) pre-made clips may not exist for every hero or pose — the video-to-robot pipeline synthesizes new ones on demand; (b) even existing clips must be velocity-clamped, IDL-remapped to the hardware joint layout, and physics-validated before they're safe to deploy.

**Q10. What would go wrong if you deployed a motion to hardware without any safety checks?**
> Without velocity clamping: joint velocities could exceed 10+ rad/s, stripping gears instantly. Without ease-in: the first command creates a violent torque snap from the current encoder position to the target. Without MotionSwitcherClient release: the built-in locomotion controller silently overrides every command you send and the robot doesn't move at all.
