# Topic 7: Physics Evaluation & Safety Systems

**What this section covers:** MuJoCo simulation validation, ZMP/CoM stability, and the full safety stack before hardware deployment.

---

## Section A — MuJoCo Physics Eval

**Q1. What does mujoco_physics_eval.py do, and where does it sit in the pipeline?**
> Runs the PKL trajectory in a MuJoCo PD-control simulation and checks ZMP and center-of-mass stability frame by frame. Sits between PKL generation/retrieval and hardware deployment — it's the last gate before a trajectory touches real hardware. If it fails, the trajectory is flagged as unsafe.

**Q2. What is ZMP (Zero Moment Point)? Why is it used to evaluate stability?**
> ZMP is the point on the ground where the net ground reaction force effectively acts (i.e., where all contact forces sum to produce zero moment). If ZMP stays within the robot's support polygon (the convex hull of all foot contact points), the robot is statically stable. If ZMP exits the polygon, the robot will tip over. It's a classical stability criterion for legged robots.

**Q3. What is the center of mass (CoM) check? What failure condition does it detect?**
> The CoM check verifies that the robot's overall center of mass projects vertically onto the support polygon. If the CoM projects outside the polygon (i.e., CoM is too far forward, backward, or sideways), the robot will inevitably fall regardless of what the legs do. This catches poses that are biomechanically impossible to hold.

**Q4. If a pose fails the physics eval, what happens next? Does the system stop or try something else?**
> The trajectory is flagged as unsafe and not sent to hardware. In the current implementation, the system reports the failure. A future improvement would be to automatically adjust the PKL (e.g., reduce arm extension angle) and re-evaluate until it passes.

**Q5. Which MuJoCo model file is used for evaluation — 23-DOF or 29-DOF? Why?**
> The 29-DOF model (`g1_29dof.xml`) for full physics accuracy — it includes all joint masses, inertias, and contact geometry. Even though the hardware is 23-DOF (joints 13-14, 20-21, 27-28 don't respond), simulating the full model gives more conservative stability estimates. Failing on 29-DOF means it's definitely unsafe on 23-DOF too.

---

## Section B — Simulation Models

**Q6. What is the difference between g1_23dof.xml, g1_29dof.xml, and g1_29dof_pinned.xml?**
> - `g1_23dof.xml` — simplified model; waist roll/pitch and wrist pitch/yaw joints removed. Matches real hardware.
> - `g1_29dof.xml` — full model with all passive joints. Better for physics accuracy in evaluation.
> - `g1_29dof_pinned.xml` — pelvis is fixed to the world (pinned). Used for arm-only testing so the robot can't fall — isolates arm joint behavior without worrying about balance.

**Q7. Why is the pinned model useful for testing arm motion specifically?**
> When testing arm trajectories (do the arms move correctly, are there collisions?), you don't want the robot to fall and interfere with the test. The pinned base holds the pelvis fixed so you can observe arm motion in isolation without needing a balanced stance. Used in the early `g1_arm_replay_airborne.py` testing phase.

**Q8. What limitations does MuJoCo simulation have that can still cause hardware failures?**
> - **Motor delay:** Real motors have latency MuJoCo doesn't model — commands arrive at 500Hz but motor response is ~1-2ms delayed.
> - **Joint friction:** Real friction is nonlinear and temperature-dependent; MuJoCo uses simplified models.
> - **Contact dynamics:** Real foot-ground contact has slip and compliance; MuJoCo contact is idealized.
> - **DDS jitter:** Real network has timing variance; simulation is deterministic.

---

## Section C — End-to-End Safety Stack

**Q9. List every layer of safety between a new PKL file and hardware execution (at least 4 layers).**
> 1. **clamp_pkls.py** — velocity clamp to ≤ 0.5 rad/s before the PKL is stored
> 2. **mujoco_physics_eval.py** — ZMP/CoM stability validation in simulation
> 3. **MotionSwitcherClient.ReleaseMode()** — ensures built-in controller doesn't override commands
> 4. **mode_machine echo** — robot rejects commands with wrong mode_machine
> 5. **3-second ease-in** — prevents torque snap from arbitrary start position
> 6. **500 Hz velocity abort (10 rad/s)** — kills all torque if any joint moves too fast during playback
> 7. **Physical: gantry suspension + L1+L2 e-stop** — human-in-the-loop kill switch

**Q10. What is the single most dangerous thing that could happen if deploy_real.py had no safety checks?**
> A PKL with a large position discontinuity between frame 0 and the robot's current position (e.g., arm at 0 rad, PKL starts at 2.5 rad) would cause an instant maximum-torque snap. At Kp=200, this could generate enough torque to strip the shoulder gearbox in milliseconds, permanently damaging the ~$90,000 robot.

**Q11. Why do you recommend gantry suspension for the first hardware test of any new animation?**
> Gantry suspension keeps the robot's feet off the ground, so any instability in the trajectory causes the robot to swing harmlessly in the harness rather than toppling and hitting the floor. A fall onto a hard floor at full torque could break joints, damage sensors, or injure nearby people. Suspension is the hardware equivalent of a simulation sandbox.

**Q12. The robot is put in DAMPING mode (L2+B) before deployment. What does DAMPING mode do?**
> DAMPING mode sets all joint gains to zero torque with soft velocity damping — the joints are backdrivable (you can move them by hand) but resist fast motion. This is the safest state to start from because: (a) no accumulated torque from a previous control mode, (b) you can manually position limbs safely, (c) it's the defined entry point before switching to low-level PD control. The button combination is L2+B on the controller.
