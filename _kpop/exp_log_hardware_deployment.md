# exp_log_hardware_deployment.md

**Objective:** Safely push `hulk_kinematics.pkl` to the physical Unitree G1 robot.
**Budget:** 15 Hypotheses
**Hypotheses Used:** 0 / 15

---

## Pre-Requisites Checklist
- [ ] Dedicated Linux Rig with real-time kernel available? `[PENDING]`
- [ ] Gantry harness installed and clear of self-collision hazards? `[PENDING]`

---

## H1: DDS UDP Network Stability

**Hypothesis:** The network layer is capable of transmitting `LowCmd_` packets at 50Hz with a jitter variance no greater than 2 milliseconds.
**Prediction:** Streaming dummy `LowCmd_` packets over `eth0` will yield 0% packet loss and a stable reception delta measured by the G1.
**Test:** Run a DDS bandwidth/jitter stress test against `192.168.123.x` before engaging any actuators.
**Result:** [PENDING]
**Verdict:** [PENDING]
**Notes:** If this falsifies (high jitter), we cannot rely on open-loop timestamped playback.

---

## H2: Playback Velocity/Torque Plausibility

**Hypothesis:** The finite differences (velocity and acceleration) extracted from consecutive frames in `hulk_kinematics.pkl` do not exceed the Unitree G1 motor specifications.
**Prediction:** A script parsing the `.pkl` and applying simple Euler differentiation (`(pos2 - pos1) / (1/fps)`) will output velocity peaks that fall entirely *under* the hardware limits for every one of the 29 servos.
**Test:** Run `deploy_real.py --dry-run` fortified with a finite-difference checker. The script will throw an anomaly flag if any generated `d_pos` vector demands impossible velocities.
**Result:** [PENDING]
**Verdict:** [PENDING]
**Notes:** A falsification here saves the hardware from ripping a gear apart. If falsified, we must apply a smoothing interpolator to the `.pkl`, or reject the choreography entirely.

---

## H3: The Gantry Stress Test (Airborne Puppet)

**Hypothesis:** The robot can physically attain the open-loop `hulk_smash` extremes in the real world without experiencing mechanical self-collision, singularity lockdown, or sudden shutdown faults.
**Prediction:** Suspended entirely from the gantry in Damping Mode (with E-Stop manned), a 0.5x speed playback of the `.pkl` will see the robot smoothly swing its arms to the overhead reach without hitting its own knees or throwing a `LowState_` fault byte.
**Test:** Physical actuation of the robot strictly on the gantry. 
**Result:** [PENDING]
**Verdict:** [PENDING]
**Notes:** As correctly established, kinematics != physics. This will *not* be tested on the ground under any circumstances until the Isaac Lab WBC handles it.
