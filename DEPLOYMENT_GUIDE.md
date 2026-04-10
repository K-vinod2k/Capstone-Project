# Unitree Output Deployment Guide

This cheat sheet guarantees you execute the strict order of operations required for both digital simulation checks and physical hardware execution on April 13th.

---

## 🖥 PART 1: The Simulation (Dry Run & Physics Validation)

**Always run this first.** Before touching the real robot, prove that the movement `.pkl` you mapped physically makes sense and doesn't shatter the ZMP (Zero Moment Point) boundary.

**Step 1: Open the Environment**
Make sure your Python environment is active on your Mac so the `mujoco` libraries are loaded.
```bash
source .venv/bin/activate
```

**Step 2: Run the Physics Evaluator**
You built the `mujoco_physics_eval.py` script specifically to act as the "Simulation QA Gatekeeper." 
```bash
python vinod_workspace/mujoco_physics_eval.py
```
**What to look for:** A local 3D rendering window will open! Watch the red Center of Mass (CoM) dot. If the robot visually trips and falls in the simulation window (its Z-height drops below `0.4`), that movement is mathematically unsafe.

**Step 3: DDS Network Simulation (Optional)**
If you want to test the raw script execution without actual physics running, use the `lo` (Local Loopback) interface on your `deploy_real.py` script. It won't move anything, but it proves your network bridge works safely without trying to broadcast over the real Ethernet.
```bash
python vinod_workspace/deploy_real.py --pkl vinod_workspace/hulk_smash_kinematics.pkl --iface lo
```

---

## 🦾 PART 2: The Real Robot (April 13th Hardware Execution)

If the simulation looks perfectly stable, you are cleared for real execution.

> [!CAUTION]
> **Safety First:** Clear a 5-foot radius around the unitree. Have an operator holding the physical remote control tightly with their fingers on **L1+L2 (Emergency Stop)**.

**Step 1: The Boot Sequence**
1. Power cycle the Unitree G1.
2. Put it in **DAMPING MODE** by pressing `L2 + A` on the physical controller. The robot will go completely limp and sink into a crumpled sitting position. 
3. Verify your Mac's Ethernet cable is plugged directly into the Unitree control module. 

**Step 2: The Test Run (Half-Speed)**
Always run the very first test at exactly half-speed (`--speed 0.5`). 
```bash
python vinod_workspace/deploy_real.py --pkl vinod_workspace/hulk_smash_kinematics.pkl --iface eth0 --speed 0.5
```
Watch the Unitree physically ease itself out of the crumpled stance into an upright stand over 3 seconds, then watch it execute the `hulk_smash` payload slowly. 

**Step 3: The Live Demo Output (Full-Speed)**
If the half-speed test works, turn it to full power!
```bash
python vinod_workspace/deploy_real.py --pkl vinod_workspace/hulk_smash_kinematics.pkl --iface eth0 --speed 1.0
```

> [!WARNING]
> If you hear grinding or the robot starts physically tipping over past 15 degrees, immediately press `Ctrl + C` in your MacOS terminal, or squeeze `L1+L2` on the controller. The PD script will catch the limit constraints and throw the robot into generic zero-torque limp compliance so it safely collapses without motor damage.
