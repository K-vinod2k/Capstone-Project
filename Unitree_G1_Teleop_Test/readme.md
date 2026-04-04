# Unitree G1 Setup Plan: Mujoco & SDK

This guide provides a step-by-step setup for `unitree_mujoco` and `unitree_sdk2_python` packages. These tools are compatible with **Linux** and **macOS** only.

## 1. Environment Setup

### Prerequisites
- Python 3.8+ (Use 3.10 - specifically as of now)
- CMake 3.10+
- GCC/Clang compiler

##### Use conda to install the packages in a conda env
- Miniconda works fine (follow setup and usage guide from official source for your os (not Windows))
- Always use conda env for easier management

### Step 1: Install CycloneDDS
Unitree SDK2 relies on CycloneDDS for communication.
```bash
git clone https://github.com/eclipse-cyclonedds/cyclonedds -b releases/0.10.x
cd cyclonedds && mkdir build install && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=../install
cmake --build . --target install
```

### Step 2: Install unitree_sdk2_python
```bash
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
cd unitree_sdk2_python
export CYCLONEDDS_HOME=/path/to/cyclonedds/install
pip3 install -e .
```

Include this at the end of your ~/.bashrc file to avoid doing it again 
```bash
export CYCLONEDDS_HOME=/path/to/cyclonedds/install
```   

### Step 3: Install unitree_mujoco

#### All runtime files are here: (updated ones are included in the current repository - you can just use this one instead of the one below)
```bash
git clone https://github.com/unitreerobotics/unitree_mujoco.git
```

#### mujoco-python
```bash
pip3 install mujoco
```

#### joystick (optional - but imports may want it)
```bash
pip3 install pygame
```

---

## 2. G1 vs. Go2 Differences

The main difference lies in the **Message IDL** and **Joint Count**.

| Feature | Unitree Go2 (Quadruped) | Unitree G1 (Humanoid) |
| :--- | :--- | :--- |
| **Message IDL** | `unitree_go` | `unitree_hg` |
| **Joint Count** | 12 (standard) | 35 (standard) |
| **Config ROBOT** | `"go2"` | `"g1"` |

---

## 3. Configuration (`config.py`)

To switch between robots, update your `config.py` in the simulation directory:

```python
# For G1
ROBOT = "g1" 
ROBOT_SCENE = "../unitree_robots/" + ROBOT + "/scene.xml"
DOMAIN_ID = 1 
INTERFACE = "lo" # Use "lo" for local simulation

## set this to 0 - disable (outside control only)
USE_JOYSTICK = 0 # Simulate Unitree WirelessController using a gamepad
```

Update scene.xml (G1 robot folder under unitree_robots):

```xml
<!-- Change this (at the start)-->
<mujoco model="g1_29dof scene">
  <include file="g1_29dof.xml"/>

<!-- to this -->
<mujoco model="g1_23dof scene">
  <include file="g1_23dof.xml"/>
```

---

## 4. Low-Level Control Logic

When writing low-level control, ensure you import the correct IDLs based on the robot type.

### Example: G1 Low-Level Initialization
```python
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_ as LowCmd_default

# Create command message
cmd = LowCmd_default()

# G1 specific init
cmd.mode_pr = 0
cmd.mode_machine = 0

# Initialize motor commands (G1 has 35 joints)
for i in range(35):
    cmd.motor_cmd[i].mode = 0x01  # PMSM mode
    cmd.motor_cmd[i].q = 0.0
    cmd.motor_cmd[i].kp = 0.0
    cmd.motor_cmd[i].dq = 0.0
    cmd.motor_cmd[i].kd = 0.0
    cmd.motor_cmd[i].tau = 0.0
```


---

## 5. High-Level Control (LocoClient)

High-level control uses the `LocoClient`. 
**Note: This is currently in development and not fully functional in the base simulation bridge without a custom server.**

### Usage Example
```python
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

client = LocoClient()
client.Init()
client.WaitLeaseApplied()

# Sequence: Damp -> Start (Stand) -> Move (Walk)
client.Damp()
time.sleep(2.0)
client.Start()
time.sleep(2.0)
client.Move(0.5, 0.0, 0.0, True) # vx=0.5m/s
```

---

## 6. Usage
> From simulation_python folder
1. **Start Simulation: (after all config changes)**
   ```bash
   python3 unitree_mujoco.py
   ```
2. **Run Control Script: (after all control code changes)**
   ```bash
   python3 test/test_unitree_sdk2.py
   ```
## Related links
- [unitree_sdk2](https://github.com/unitreerobotics/unitree_sdk2)
- [unitree_sdk2_python](https://github.com/unitreerobotics/unitree_sdk2_python)
- [Unitree Doc](https://support.unitree.com/home/zh/developer)
- [Mujoco Doc](https://mujoco.readthedocs.io/en/stable/overview.html)
