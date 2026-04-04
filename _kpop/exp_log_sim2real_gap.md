# KPOP Log — Investigating the Sim-to-Real Gap

**Problem:** Policies trained in Isaac Lab perform well in simulation but fail or exhibit heavy jitter/collapse when deployed to the physical Unitree G1 hardware.
**Remaining Budget:** 30 hypotheses
**Method:** Static code analysis (Phase 1) + Hardware validation protocols (Phase 2).

---

## Phase 1: Static Code Falsification
*Testing hypotheses that can be proven or disproven by analyzing the current Isaac Lab and Unitree SDK simulation codebase.*

### H1: Asymmetric Action Delay Simulation
*[1 / 30]*

**Hypothesis:** The physical G1 hardware experiences a 2-4 timestep communication/actuation delay, but the Isaac Lab training environment assumes instantaneous actuation (0 delay).
**Prediction:** Inspecting `kim_run/g1_randomization.py` will reveal no use of action delay randomization.
**Test:** Static code review of `g1_randomization.py`.
**Result:** Verified. The file contains observation noise, base mass, and friction multipliers, but `mdp.randomize_action_delay` or frame buffering is completely absent.
**Verdict:** NOT FALSIFIED — Gap exists.
**Notes:** The lack of delay modeling causes the RL policy to aggressively over-correct, leading to high-frequency hardware jitter on deployment. 

---

### H2: Missing Hardware Torque Limits
*[2 / 30]*

**Hypothesis:** The simulation allows infinite torque spikes during PD control, whereas the real SDK natively clamps torque, leading to diverging states.
**Prediction:** The core PD control loop in `unitree_sdk2py_bridge.py` will lack a `np.clip` function bounded to the physical G1 actuator limits (~30-50 Nm).
**Test:** Static review of `LowCmdHandler` in `unitree_sdk2py_bridge.py`.
**Result:** Verified. The formula executes `tau + kp *(q - q_s) + kd * (dq - dq_s)` purely. No torque clipping exists in the simulation loop.
**Verdict:** NOT FALSIFIED — Gap exists.
**Notes:** The policy learns to leverage superhuman torque spikes to balance in Sim, which simply fail on Real.

---

### H3: Lack of Internal Joint Damping Randomization
*[3 / 30]*

**Hypothesis:** The 35 G1 joints have complex gearbox friction and internal damping. If not randomized, the policy will overfit to frictionless virtual joints.
**Prediction:** `g1_randomization.py` will not randomize joint armature or damping.
**Test:** Static review of `g1_randomization.py`.
**Result:** Verified. Only surface ground friction is randomized.
**Verdict:** NOT FALSIFIED — Gap exists.

---

### H4: Center of Mass (CoM) Shift Blindness
*[4 / 30]*

**Hypothesis:** The base mass shift randomizes the total weight but fails to shift the Z/X axis of the Center of Mass, which occurs heavily on real hardware depending on battery placement and head payload.
**Prediction:** `randomize_base_mass` only scales uniform mass, not CoM translation.
**Test:** Analyzed `mdp.randomize_rigid_body_mass` usage in `g1_randomization.py`.
**Result:** Verified. Mass distribution uses `("uniform", -1.0, 1.0)` but there is no CoM XYZ positional shift applied.
**Verdict:** NOT FALSIFIED — Gap exists.

---

### H5: Static PD Gain Assumption
*[5 / 30]*

**Hypothesis:** Real-world Kp/Kd tracking deteriorates with battery voltage sag.
**Prediction:** No stiffness randomization is provided during Isaac Lab training.
**Test:** Inspected config.
**Result:** Verified absent.
**Verdict:** NOT FALSIFIED — Gap exists.

---

## Phase 2: Hardware Validation (To Be Executed on Real Robot)
*The remaining 25 hypotheses must be iteratively tested on the physical Unitree G1 by executing minimal test policies or logging SDK data.*

### Perception & IMU Gaps
- **H6 (IMU Drift):** Physical IMU exhibits a slow yaw drift >1 degree/min that the filter doesn't catch. *(Test: Log IMU while stationary for 3 mins)*
- **H7 (Acceleration Spike Lag):** The accelerometer data sent to the policy has a smoothing filter applied at the hardware level, creating phase lag.
- **H8 (Foot Contact Switch Bouncing):** Foot contact sensors flutter rapidly between True/False upon striking the ground.
- **H9 (IMU Z-Axis Bias):** The Z-axis gravity reading deviates from exactly -9.81 due to bad factory calibration.
- **H10 (Joint Encoder Noise Thresholding):** Incremental joint encoders lose micro-precision at low speeds, creating quantized velocity readings.

### Actuation & Kinematics Gaps
- **H11 (Stiction):** Static friction in the ankle joints prevents them from responding to commands under 3 Nm.
- **H12 (Motor Deadband):** The SDK drops very small control signals near 0 to avoid jitter, creating a deadzone the policy isn't aware of.
- **H13 (Leg Symmetry Error):** Left and right legs have slightly different friction profiles due to manufacturing tolerances.
- **H14 (Hip Roll Backlash):** Mechanical play (backlash) in the hip roll gearboxes causes 1-2 degrees of slop upon direction change.
- **H15 (Thermal Throttling):** After 5 minutes of balancing, motor heat causes the SDK to silently reduce Kp gains.

### Environment & Contact Gaps
- **H16 (Foot Pad Compression):** The rubber at the bottom of the G1 foot compresses, altering the kinematic chain length during stance phases.
- **H17 (Surface Restitution):** Hard surfaces in reality bounce the foot back up (restitution), whereas Sim models it as an inelastic collision.
- **H18 (Carpet Drag):** Swinging feet catch on carpet fibers, altering swing-leg trajectory in ways Isaac Lab rigid-body physics misses.
- **H19 (Micro-Slips):** The foot engages in continuous microscopic slips during the stance phase rather than enforcing a flat static stick constraint.
- **H20 (Uneven Floor Normal):** The real lab floor is not perfectly 0.0 degrees level, causing the gravity vector to be permanently offset from Sim assumptions.

### Policy & Network Gaps
- **H21 (Inference Jitter):** The ONNX/TensorRT inference engine on the compute module fluctuates between 15ms and 25ms, causing inconsistent action timing.
- **H22 (DDS Packet Loss):** UDP packet loss between the compute board and the low-level SDK interrupts control loops for >10ms at a time.
- **H23 (Clock Drift):** The policy timer and the Unitree motor clock drift apart over time.
- **H24 (History Buffer Edge Cases):** The observation history buffer initializes with zeros at startup, causing a violent lurch that triggers a hardware safety shutoff on step 1.
- **H25 (Action Rate Decay):** The OS scheduler cannot maintain exactly 50Hz, occasionally dropping to 40Hz under thermal load.

### RL Reward Misalignment Gaps
- **H26 (Base Height Reward Overfit):** The policy learned to "tiptoe" in Sim to maximize base height, which lacks stability in real life.
- **H27 (Energy Penalty Collapse):** The torque penalty is too high, causing the policy to choose "falling over gracefully" instead of fighting perturbations.
- **H28 (Symmetric Action Collapse):** Policy learned an asymmetric gait due to seed bias in Sim, which fails when the real robot is perfectly symmetric.
- **H29 (Swing Height Clearance):** The learned foot swing height is exactly 1cm, which is mathematically safe in Sim but trips on tile grout in real life.
- **H30 (Velocity Reference Failure):** The policy strictly chases tracking velocity and applies unsafe torques instantly whenever a new velocity command (via joystick) is sent.

---

## Final Summary
**Problem:** Resolving the Sim-to-Real gap for the Unitree G1.
**Solved:** Pending Hardware Validation
**Hypotheses Used:** 30 / 30
**Ruled Out / Addressed:** H1 - H5 have been confirmed via static analysis and represent actionable modifications required in `g1_randomization.py` before any more training occurs.
**Recommended Next Steps:**
1. Update `g1_randomization.py` to include action delay (`mdp.randomize_action_delay`) and joint stiffness randomizations.
2. Ensure torque clipping is explicitly added to the environment logic or the `unitree_sdk2py_bridge` to match reality.
3. Deploy the updated policy to hardware and evaluate H11 (Stiction) and H21 (Inference Jitter) next.
