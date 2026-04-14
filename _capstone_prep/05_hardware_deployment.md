# Topic 5: Hardware Deployment & Robot Control

**What this section covers:** How PKL trajectories are executed on real hardware — DDS, PD control, safety systems, and joint mapping.

---

## Section A — Communication (DDS)

**Q1. What is DDS? Why does the Unitree G1 use it instead of something simpler like TCP/HTTP?**
> DDS (Data Distribution Service) is a publish-subscribe middleware standard designed for real-time embedded systems. The G1 uses it because: (a) deterministic latency — critical for 500 Hz control loops, (b) automatic discovery — no manual connection setup needed on the same subnet, (c) QoS policies for reliable delivery. TCP/HTTP introduces variable latency and has no native pub-sub model suitable for high-frequency sensor/actuator loops.

**Q2. What is the difference between rt/lowcmd and rt/lowstate topics?**
> `rt/lowstate` — robot publishes to this: encoder positions (q), velocities (dq), IMU data, mode_machine. Computer subscribes to read the robot's current state.
> `rt/lowcmd` — computer publishes to this: 35 motor commands (q target, kp, kd, tau, mode). Robot subscribes and executes them.

**Q3. What is CycloneDDS, and why does Linux not need a CYCLONEDDS_URI but macOS does?**
> CycloneDDS is the open-source DDS implementation bundled with unitree_sdk2py. On Linux with direct Ethernet to the robot (same subnet), CycloneDDS multicast auto-discovers the robot — no explicit peer configuration needed. On macOS, the network stack handles multicast differently, so you must set `CYCLONEDDS_URI` with an explicit `<Peer address="192.168.123.164"/>` to force unicast discovery.

**Q4. What is mode_machine, and what happens if you send a LowCmd with the wrong value?**
> `mode_machine` is a field in LowCmd that must match the robot's current operational mode (read from LowState). If it doesn't match, the robot **silently discards every command** — no error, no movement, no feedback. This was the root cause of the "robot doesn't move" bug: we hardcoded `mode_machine=0` but the robot was in `mode_machine=4`. Fix: read `msg.mode_machine` from the first LowState and echo it in every LowCmd.

**Q5. Why do you call MotionSwitcherClient.ReleaseMode() before sending PD commands?**
> The G1 ships with a built-in high-level locomotion controller (balance mode, walk mode). This controller runs on the robot's onboard CPU and **overrides all low-level PD commands** at the LowCmd level. Without calling `ReleaseMode()`, you can send perfect commands all day and the robot won't move — the built-in controller cancels them. This was another root cause of no movement in early tests.

---

## Section B — PD Control

**Q6. What is PD control? Explain Kp and Kd in plain terms.**
> PD = Proportional-Derivative control. For each joint:
> `torque = Kp × (q_target − q_current) + Kd × (0 − dq_current)`
> **Kp (proportional):** stiffness — how hard the joint fights to reach the target position. High Kp = stiff/rigid.
> **Kd (derivative):** damping — how much the joint resists velocity. High Kd = sluggish, resists fast motion.

**Q7. Why do legs use Kp=200 and arms use Kp=60? What would happen if you used Kp=200 on the arms?**
> Legs must support the robot's full body weight (~16kg) against gravity — high rigidity (Kp=200) is needed to hold the stance. Arms carry no load and need smooth, fluid motion. Kp=200 on arms would cause violent snapping to target positions — dangerous for the gears and visually jerky. Kp=60 gives compliant tracking.

**Q8. What does the ease-in phase do, and why is it 3 seconds long?**
> The ease-in linearly interpolates from the robot's **current encoder position** (wherever the arms happen to be resting) to the **first frame of the PKL** over 3 seconds. Without this, the very first command could be a huge position error (e.g., arm at 0 rad, PKL starts at 1.5 rad) causing an instant violent torque snap. 3 seconds is slow enough to be safe and fast enough not to be awkward.

**Q9. The control loop runs at 500 Hz but the PKL was recorded at 30 FPS. How does the script handle this mismatch?**
> Floating-point frame index: `float_idx = t × active_fps` where `active_fps = 30 × speed_factor`. Then linear interpolation between `frames[floor(float_idx)]` and `frames[ceil(float_idx)]` weighted by `alpha = float_idx − floor`. This produces smooth 500 Hz motion from 30 FPS keyframes.

**Q10. What is the velocity abort threshold, and why is it set to 10 rad/s?**
> `VELOCITY_ABORT_THRESHOLD = 10.0` rad/s. At every tick, if any joint's encoder velocity (`motor_state[i].dq`) exceeds this, all torques are killed instantly. 10 rad/s ≈ 573 degrees/second — fast enough to indicate runaway/oscillation, but not triggered by normal motion (PKLs are clamped to 0.5 rad/s). Protects hardware gears from high-velocity impacts.

---

## Section C — Joint Mapping

**Q11. What is the G1 23-DOF hardware IDL? Where do arm joints start — index 13 or 15? How do you know?**
> Arms start at **index 13** on the 23-DOF hardware. Confirmed from the KatzAIM/Unitree_G1_Teleop_Test repo's `g1_joint_index_dds.md` which documents the 23-DOF IDL explicitly:
> `13=L_SHOULDER_PITCH, 14=L_SHOULDER_ROLL, 15=L_SHOULDER_YAW, 16=L_ELBOW_PITCH, 17=L_ELBOW_ROLL, 18=R_SHOULDER_PITCH ...`
> Index 15 is where arms start on the 29-DOF model. The confusion between these two caused a long debugging session.

**Q12. What did remap_23dof.py do, and was it correct?**
> It remapped PKL data from 29-DOF layout (arms at 15-28) to 23-DOF hardware IDL (arms at 13-22), dropping wrist joints that don't exist on 23-DOF. The mapping was correct. Dropped: waist_roll/pitch (passive), wrist_pitch/yaw (no hardware). The confusion arose when we temporarily thought it was wrong and restored the 29-DOF PKLs — this broke arm motion entirely.

**Q13. What is clamp_pkls.py doing, and why is MAX_VEL=0.5 rad/s the right safety limit?**
> It upsamples PKL frames so no joint moves faster than MAX_VEL between consecutive frames. E.g., if shoulder pitch moves 1.0 rad over 1 frame at 30 FPS = 30 rad/s — catastrophically dangerous. Upsampling inserts interpolated frames until the per-frame delta stays ≤ 0.5/30 = 0.0167 rad/frame. Result: hulk_smash goes from 187 → 726 frames. 0.5 rad/s is 20× below the abort threshold (10 rad/s), giving safe margin.

**Q14. If you command joint index 19 (R_shoulder_roll) with a negative value, what physically happens?**
> Currently under investigation — the right arm shoulder roll appears to move the arm **inward** (adduction toward the body) when commanded negative, while the PKL has negative values expecting outward motion. A sign flip on index 19 is being tested to verify if this corrects the asymmetry between left and right arm motion.

---

## Section D — Safety

**Q15. List every safety mechanism in deploy_real.py from first to last.**
> 1. **MotionSwitcherClient.ReleaseMode()** — ensures built-in controller isn't overriding commands
> 2. **mode_machine echo** — robot won't accept commands with wrong mode_machine
> 3. **3-second ease-in** — prevents torque snap from arbitrary start position
> 4. **Velocity abort (10 rad/s)** — checked every tick; kills all torque on any joint exceeding threshold
> 5. **_kill() zero-torque** — always called at end; robot goes limp safely
> 6. **clamp_pkls.py preprocessing** — PKL data already limited to 0.5 rad/s before deploy

**Q16. What does _kill() do, and why does it send 15 commands rather than one?**
> Sends 15 zero-gain, zero-target LowCmd messages spaced 10ms apart (total 150ms). One command might get lost in DDS. Sending 15 ensures the robot definitely receives the zero-torque signal before going fully limp. It then prints "Robot is safe to handle."

**Q17. What physical safety precautions must be in place before running deploy_real.py?**
> 1. Robot physically cleared of obstacles in all directions
> 2. Gantry suspension recommended for first test of any new animation
> 3. Robot booted in DAMPING mode (L2+B on controller) — joints are backdrivable, not locked
> 4. Operator holding L1+L2 physical e-stop, ready to engage instantly

---

## Section E — G1 EDU Architecture (New Research)

**Q18. The G1 EDU has two computers. What are they and what does each do?**
> - `192.168.123.161` — **Locomotion computer**: runs Unitree's proprietary balance/locomotion black box. No SSH access. You cannot touch this.
> - `192.168.123.164` — **Development computer**: Jetson Orin NX, SSH credentials `unitree/123`. Your code runs here. This is where deploy_real.py executes.

**Q19. Can the G1 walk and do hero arm poses at the same time?**
> **No — and this is an open research question.** Unitree has not provided an official API for running the locomotion controller (balance/walk) simultaneously with low-level arm commands. The current approach releases motion mode entirely (`MotionSwitcherClient.ReleaseMode()`), giving full low-level control over all joints — meaning the robot stands stationary while performing hero poses. Whole-body control (locomotion + manipulation simultaneously) requires a custom RL policy trained end-to-end.

**Q20. What is the ankle PR mode vs AB mode, and which does your code use?**
> The G1 ankle uses a parallel mechanism with two control modes:
> - **PR Mode (mode_pr=0):** Controls pitch and roll angles directly, matching the URDF convention. Default and used in deploy_real.py.
> - **AB Mode (mode_pr=1):** Directly controls the A and B actuator motors — user must compute parallel mechanism kinematics manually.
> deploy_real.py always uses PR mode (mode_pr=0), which is correct for normal operation.

**Q21. How would you improve SMPL-X → G1 joint angle retargeting beyond the current GMR approach?**
> Use **Pinocchio** with CasADi bindings for proper inverse kinematics:
> ```bash
> conda install -c conda-forge "pinocchio>=3.0.0,<4.0.0"
> ```
> Pinocchio loads the G1 URDF and solves per-limb IK from SMPL-X end-effector targets to G1 joint space. Advantage over GMR: exact IK respects joint limits, handles the DOF mismatch explicitly, and produces smooth trajectories. LeRobot uses this approach for G1 arm teleoperation.

**Q22. If a judge asks "can the robot walk while doing the pose?" — how do you answer?**
> "That's a great question and an active research problem. The G1's locomotion controller and low-level arm control currently can't run simultaneously without a custom whole-body controller. Our project demonstrates expressive arm poses from natural language — the standing stationary case. Combining locomotion + arm expression requires training a single RL policy for the whole body, which is future work using Isaac Lab or unitree_rl_gym."
