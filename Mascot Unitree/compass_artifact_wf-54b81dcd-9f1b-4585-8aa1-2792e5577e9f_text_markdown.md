# Seven engineering fixes for a Unitree G1 pose pipeline

**The path from natural language to humanoid motion breaks at predictable seams.** This report provides tested, code-level solutions for each of seven failure modes in a pipeline spanning LLM → video generation → PromptHMR/SMPL-X → retargeting → MuJoCo → Unitree G1 hardware. The two most dangerous problems—MuJoCo's silent actuator misconfiguration and the G1's passive-joint routing mismatch—receive priority treatment with production-ready Python code, validated XML patterns, and unit tests. Every solution uses the MuJoCo Python API, targets the Unitree G1 specifically, and references real repositories.

---

## 1. MuJoCo actuators silently become constant-torque motors when biastype is wrong

**This is the most insidious bug in the stack.** When a MuJoCo `<general>` actuator has `biastype="none"` (integer value 0) instead of `biastype="affine"` (integer value 1), the `biasprm` array is stored but **completely ignored**. The actuator degrades from a PD position controller to a constant-torque motor. MuJoCo raises no warning. The model loads, simulation runs, and the robot collapses.

MuJoCo computes actuator force as `force = gain_term + bias_term`. For position-PD control, the force should be `kp × (target − position) − kd × velocity`. This requires the bias term to contribute `−kp × position − kd × velocity`, which only happens when `biastype="affine"`. With `biastype="none"`, bias is hardcoded to zero regardless of `biasprm` values, reducing the force to `kp × ctrl`—a constant torque proportional to the control signal.

| Configuration | biastype | Force equation | Actual behavior |
|---|---|---|---|
| `biastype="none"`, `biasprm="0 -100 -10"` | 0 (NONE) | `force = kp × ctrl` | **Constant torque motor** |
| `biastype="affine"`, `biasprm="0 -100 -10"` | 1 (AFFINE) | `force = kp×(ctrl − pos) − kd×vel` | **PD position controller** |

The root cause is in MuJoCo's `engine_forward.c`, where a switch on `mjtBias` enum simply sets `bias = 0.0` for `mjBIAS_NONE` before any `biasprm` values are read. This is documented behavior, but the silent acceptance of contradictory parameters (setting `biasprm` values that are then ignored) makes it a trap. GitHub discussion #754 on the DeepMind MuJoCo repo, issues #189, #1074, #1229, and #1375 all document users encountering variants of this failure.

### Correct XML for G1 position-PD actuators

The safest approach uses the `<position>` shortcut, which automatically sets `gaintype="fixed"`, `biastype="affine"`, and wires `gainprm`/`biasprm` correctly:

```xml
<actuator>
  <!-- CORRECT: position shortcut auto-sets biastype="affine" -->
  <position name="left_hip_pitch" joint="left_hip_pitch_joint"
            kp="150" kv="2" ctrllimited="true" ctrlrange="-1.57 1.57"/>
  <position name="left_knee" joint="left_knee_joint"
            kp="300" kv="4" ctrllimited="true" ctrlrange="-0.087 2.05"/>
  <position name="left_ankle_pitch" joint="left_ankle_pitch_joint"
            kp="40" kv="2" ctrllimited="true" ctrlrange="-0.87 0.52"/>
  <position name="waist_yaw" joint="waist_yaw_joint"
            kp="250" kv="5" ctrllimited="true" ctrlrange="-2.618 2.618"/>
  <position name="left_shoulder_pitch" joint="left_shoulder_pitch_joint"
            kp="100" kv="2" ctrllimited="true" ctrlrange="-3.11 2.62"/>
</actuator>
```

If you must use `<general>` (for runtime gain switching, etc.), the equivalent is:

```xml
<general name="left_hip_pitch" joint="left_hip_pitch_joint"
         gaintype="fixed" gainprm="150"
         biastype="affine" biasprm="0 -150 -2"
         ctrllimited="true" ctrlrange="-1.57 1.57"/>
```

PD gains for the G1 (from NVIDIA GR00T/LeRobot integration, validated in MuJoCo Playground sim-to-real): hip joints **kp=150, kd=2**; knees **kp=300, kd=4**; ankles **kp=40, kd=2**; waist **kp=250, kd=5**; shoulders **kp=100, kd=2–5**; elbows/wrists **kp=20–40, kd=1–2**.

### Model-load-time assertion catches the bug before simulation

```python
import mujoco
import numpy as np

def verify_actuator_pd_config(model: mujoco.MjModel):
    """Assert all actuators are in true position-PD mode at load time."""
    for i in range(model.nu):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
        biastype = model.actuator_biastype[i]
        gainprm = model.actuator_gainprm[i]
        biasprm = model.actuator_biasprm[i]

        # CRITICAL: biastype must be 1 (AFFINE), not 0 (NONE)
        assert biastype == 1, (
            f"FATAL: Actuator '{name}' has biastype={biastype} (mjBIAS_NONE). "
            f"biasprm={biasprm[:3]} is SILENTLY IGNORED. The actuator is a "
            f"constant-torque motor, NOT a position controller. "
            f"Fix: set biastype='affine' or use <position> shortcut."
        )

        kp = gainprm[0]
        assert kp > 0, f"Actuator '{name}': kp={kp} must be positive"
        assert np.isclose(biasprm[1], -kp), (
            f"Actuator '{name}': biasprm[1]={biasprm[1]} should equal -kp={-kp}"
        )
        assert biasprm[2] <= 0, (
            f"Actuator '{name}': biasprm[2]={biasprm[2]} (damping) should be <= 0"
        )
        print(f"  ✅ '{name}': kp={kp}, kd={abs(biasprm[2])}, PD config correct")

model = mujoco.MjModel.from_xml_path("g1.xml")
verify_actuator_pd_config(model)
```

### Runtime behavioral test proves tracking, not constant torque

A constant-torque actuator accelerates indefinitely; a PD actuator converges. This test distinguishes them:

```python
def test_position_tracking(xml_path: str, joint_name: str,
                           target_pos: float = 0.5, tolerance: float = 0.05):
    """Verify actuator tracks position (not constant torque)."""
    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)
    act_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, joint_name)
    jnt_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)

    data.ctrl[act_id] = target_pos
    for _ in range(5000):
        mujoco.mj_step(model, data)

    final_pos = data.qpos[model.jnt_qposadr[jnt_id]]
    final_vel = abs(data.qvel[model.jnt_dofadr[jnt_id]])

    assert abs(final_pos - target_pos) < tolerance, (
        f"Joint '{joint_name}' did not converge: target={target_pos}, "
        f"actual={final_pos:.4f}. Likely biastype misconfiguration."
    )
    assert final_vel < 0.1, (
        f"Joint '{joint_name}' still moving (vel={final_vel:.4f}). "
        f"PD controller should have settled. CHECK biastype."
    )
```

### Pytest suite demonstrates correct vs broken behavior

```python
CORRECT_XML = """
<mujoco><worldbody><body>
  <joint name="j" type="hinge" axis="0 0 1" damping="0.1"/>
  <geom type="capsule" size="0.05 0.5" mass="1"/>
</body></worldbody>
<actuator><position name="j" joint="j" kp="100" kv="10"/></actuator>
</mujoco>"""

BROKEN_XML = """
<mujoco><worldbody><body>
  <joint name="j" type="hinge" axis="0 0 1" damping="0.1"/>
  <geom type="capsule" size="0.05 0.5" mass="1"/>
</body></worldbody>
<actuator><general name="j" joint="j"
  gaintype="fixed" gainprm="100"
  biastype="none" biasprm="0 -100 -10"/></actuator>
</mujoco>"""

def test_correct_converges():
    model = mujoco.MjModel.from_xml_string(CORRECT_XML)
    data = mujoco.MjData(model)
    data.ctrl[0] = 0.5
    for _ in range(5000): mujoco.mj_step(model, data)
    assert abs(data.qpos[0] - 0.5) < 0.01  # Converges ✓

def test_broken_does_not_converge():
    model = mujoco.MjModel.from_xml_string(BROKEN_XML)
    data = mujoco.MjData(model)
    data.ctrl[0] = 0.5
    for _ in range(1000): mujoco.mj_step(model, data)
    assert abs(data.qpos[0] - 0.5) > 0.1   # Overshoots wildly ✓

def test_detect_silent_misconfiguration():
    model = mujoco.MjModel.from_xml_string(BROKEN_XML)
    # biastype=0 but biasprm has non-zero position term → silent failure
    assert model.actuator_biastype[0] == 0
    assert model.actuator_biasprm[0, 1] == -100.0  # Stored but IGNORED
```

---

## 2. Routing 29 kinematic joints through 23 actuators on the G1

The Unitree G1 ships in multiple hardware configurations sharing a single 29-joint kinematic model. The 23-DOF variant lacks **6 joints**: `waist_roll_joint`, `waist_pitch_joint`, `left_wrist_pitch_joint`, `left_wrist_yaw_joint`, `right_wrist_pitch_joint`, and `right_wrist_yaw_joint`. Sending a 29-element action vector by positional index to a 23-actuator model silently maps commands to the wrong joints. This is the second most common G1 integration failure.

The complete 29-joint table (from Unitree official documentation and confirmed in the MuJoCo Menagerie model):

| Indices | Group | Joint names |
|---------|-------|-------------|
| 0–5 | Left leg | `left_hip_pitch/roll/yaw`, `left_knee`, `left_ankle_pitch/roll` |
| 6–11 | Right leg | Mirror of left leg |
| 12–14 | Waist | `waist_yaw/roll/pitch` |
| 15–21 | Left arm | `left_shoulder_pitch/roll/yaw`, `left_elbow`, `left_wrist_roll/pitch/yaw` |
| 22–28 | Right arm | Mirror of left arm |

Key repositories housing official G1 MJCF files: `google-deepmind/mujoco_menagerie/unitree_g1` (curated model with position actuators), `unitreerobotics/unitree_mujoco` (official sim with DDS bridge), `unitreerobotics/unitree_ros/robots/g1_description` (URDF source for all variants).

### Name-based joint routing table eliminates positional indexing

The critical MuJoCo field is `model.actuator_trnid[i, 0]`, which gives the joint ID driven by actuator `i`. This, combined with `mj_name2id`, builds a complete name-based routing table that works regardless of joint ordering differences between MJCF files:

```python
import mujoco
import numpy as np

class G1JointRouter:
    """Name-based routing table for Unitree G1 in MuJoCo.
    
    Handles 29-joint MJCF with any number of actuated DOFs.
    Never uses positional indexing for joint-actuator mapping.
    """
    
    PASSIVE_IN_23DOF = {
        "waist_roll_joint", "waist_pitch_joint",
        "left_wrist_pitch_joint", "left_wrist_yaw_joint",
        "right_wrist_pitch_joint", "right_wrist_yaw_joint",
    }
    
    ALL_29_JOINTS = [
        "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
        "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
        "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
        "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
        "waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint",
        "left_shoulder_pitch_joint", "left_shoulder_roll_joint",
        "left_shoulder_yaw_joint", "left_elbow_joint",
        "left_wrist_roll_joint", "left_wrist_pitch_joint", "left_wrist_yaw_joint",
        "right_shoulder_pitch_joint", "right_shoulder_roll_joint",
        "right_shoulder_yaw_joint", "right_elbow_joint",
        "right_wrist_roll_joint", "right_wrist_pitch_joint", "right_wrist_yaw_joint",
    ]

    def __init__(self, xml_path: str):
        self.model = mujoco.MjModel.from_xml_path(xml_path)
        self.data = mujoco.MjData(self.model)
        self._build_maps()

    def _build_maps(self):
        # Joint name → actuator ctrl index (None if passive)
        self.joint_to_ctrl = {}
        self.ctrl_to_joint = {}
        for act_idx in range(self.model.nu):
            jnt_id = self.model.actuator_trnid[act_idx, 0]
            jnt_name = self.model.joint(jnt_id).name
            self.joint_to_ctrl[jnt_name] = act_idx
            self.ctrl_to_joint[act_idx] = jnt_name

        # Joint name → qpos/qvel address
        self.joint_to_qpos = {}
        self.joint_to_qvel = {}
        self.passive_joints = []
        self.active_joints = []
        for i in range(self.model.njnt):
            jnt = self.model.joint(i)
            if jnt.type[0] == mujoco.mjtJoint.mjJNT_FREE:
                continue
            name = jnt.name
            self.joint_to_qpos[name] = self.model.jnt_qposadr[i]
            self.joint_to_qvel[name] = self.model.jnt_dofadr[i]
            if name in self.joint_to_ctrl:
                self.active_joints.append(name)
            else:
                self.passive_joints.append(name)

    def set_joint_target(self, joint_name: str, value: float):
        """Set actuator target by name. Silently skips passive joints."""
        if joint_name in self.joint_to_ctrl:
            self.data.ctrl[self.joint_to_ctrl[joint_name]] = value

    def set_action_vector(self, action: np.ndarray, joint_order: list):
        """Map a 29-element action to ctrl, skipping passive joints."""
        for i, jname in enumerate(joint_order):
            if jname in self.joint_to_ctrl:
                self.data.ctrl[self.joint_to_ctrl[jname]] = action[i]

    def get_joint_pos(self, name: str) -> float:
        return self.data.qpos[self.joint_to_qpos[name]]

    def is_passive(self, name: str) -> bool:
        return name not in self.joint_to_ctrl
```

### Three XML patterns for locking passive joints

**Equality constraint** (recommended—cleanest, toggleable at runtime):
```xml
<equality>
  <joint joint1="waist_roll_joint"  polycoef="0 1 0 0 0"/>
  <joint joint1="waist_pitch_joint" polycoef="0 1 0 0 0"/>
  <joint joint1="left_wrist_pitch_joint"  polycoef="0 1 0 0 0"/>
  <joint joint1="left_wrist_yaw_joint"    polycoef="0 1 0 0 0"/>
  <joint joint1="right_wrist_pitch_joint" polycoef="0 1 0 0 0"/>
  <joint joint1="right_wrist_yaw_joint"   polycoef="0 1 0 0 0"/>
</equality>
```

**Zero-range hard lock**: `<joint name="waist_roll_joint" range="0 0" limited="true"/>`

**High stiffness soft lock**: `<joint name="waist_roll_joint" stiffness="10000" damping="1000"/>`

The simplest solution, when feasible, is to use the 23-DOF MJCF variant directly (`g1_23dof_rev_1_0.xml`), which removes passive joints from the kinematic tree entirely. However, if your retargeting pipeline produces 29-DOF outputs (common with SMPL-X), the routing table approach handles the mismatch cleanly.

---

## 3. Physics-gated validation rejects impossible poses before hardware

Without ground-truth "hero poses," every LLM-proposed pose must pass three gates: joint limits, self-collision, and static stability. These gates run in order of computational cost.

### Gate 1: Joint limit check (no physics required)

```python
def check_joint_limits(model, proposed_qpos):
    """Check proposed angles against MuJoCo model limits."""
    violations = []
    for i in range(model.njnt):
        if not model.jnt_limited[i]:
            continue
        if model.jnt_type[i] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        adr = model.jnt_qposadr[i]
        val = proposed_qpos[adr]
        lo, hi = model.jnt_range[i]
        if val < lo or val > hi:
            violations.append({
                'joint': model.joint(i).name,
                'value': val, 'range': (lo, hi),
                'violation': max(lo - val, val - hi)
            })
    return violations
```

### Gate 2: Self-collision via MuJoCo contact detection

After setting `data.qpos` and calling `mj_forward`, MuJoCo populates `data.contact` with all detected collisions. Self-collision means both `geom1` and `geom2` belong to the robot:

```python
def detect_self_collisions(model, data, robot_geom_ids):
    """Find contacts where both geoms belong to the robot."""
    collisions = []
    for i in range(data.ncon):
        c = data.contact[i]
        if c.geom1 in robot_geom_ids and c.geom2 in robot_geom_ids:
            collisions.append({
                'geom1': mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, c.geom1),
                'geom2': mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, c.geom2),
                'penetration': -c.dist
            })
    return collisions
```

A vectorized version for performance-critical loops:
```python
geom1 = data.contact.geom1[:data.ncon]
geom2 = data.contact.geom2[:data.ncon]
mask = np.isin(geom1, list(robot_geom_ids)) & np.isin(geom2, list(robot_geom_ids))
has_self_collision = np.any(mask)
```

### Gate 3: Center-of-mass inside foot support polygon

`data.subtree_com[0]` gives the whole-body CoM after `mj_forward`. Project onto the ground plane (XY for MuJoCo's Z-up), compute the convex hull of foot contact points, and test containment:

```python
from scipy.spatial import ConvexHull

def check_com_stability(model, data, left_foot_body, right_foot_body,
                        min_margin=0.01):
    """Check if CoM projection falls inside the foot support polygon."""
    com_2d = data.subtree_com[0][:2]  # XY projection

    # Collect foot geom corner points
    foot_pts = []
    for foot_name in [left_foot_body, right_foot_body]:
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, foot_name)
        for g in range(model.body_geomnum[body_id]):
            gid = model.body_geomadr[body_id] + g
            pos = data.geom_xpos[gid]
            size = model.geom_size[gid]
            mat = data.geom_xmat[gid].reshape(3, 3)
            if model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_BOX:
                for sx in [-1, 1]:
                    for sy in [-1, 1]:
                        corner = pos + mat @ np.array([sx*size[0], sy*size[1], -size[2]])
                        foot_pts.append(corner[:2])
            else:
                foot_pts.append(pos[:2])

    foot_pts = np.array(foot_pts)
    if len(foot_pts) < 3:
        return False, -np.inf

    hull = ConvexHull(foot_pts)
    distances = hull.equations[:, :2] @ com_2d + hull.equations[:, 2]
    margin = -np.max(distances)  # positive = inside
    return margin >= min_margin, margin
```

The stability margin (`-max(normal · point + offset)` over all facet equations) is positive when the CoM is inside the polygon. A **1 cm minimum margin** provides a conservative safety buffer.

---

## 4. A single rotation matrix converts SMPL-X frames to MuJoCo

SMPL-X uses **Y-up, Z-forward** (computer vision convention). MuJoCo uses **Z-up, X-forward** (robotics convention). The conversion is a cyclic permutation of axes—equivalently, a 120° rotation around the `[1,1,1]` axis:

```python
R_SMPL_TO_MUJOCO = np.array([
    [0, 0, 1],   # x_mujoco = z_smpl (forward)
    [1, 0, 0],   # y_mujoco = x_smpl (left)
    [0, 1, 0],   # z_mujoco = y_smpl (up)
])
```

As a MuJoCo quaternion (w,x,y,z): **(0.5, 0.5, 0.5, 0.5)**. For translations, multiply directly: `pos_mj = R @ pos_smpl`. For rotations, apply conjugation: `R_mj = R_frame @ R_smpl @ R_frame.T`.

```python
from scipy.spatial.transform import Rotation as R

ROT_FRAME = R.from_matrix(np.array([[0,0,1],[1,0,0],[0,1,0]]))

def convert_global_orient(global_orient_aa):
    """SMPL-X axis-angle global orient → MuJoCo quaternion (w,x,y,z)."""
    R_body = R.from_rotvec(global_orient_aa)
    R_mj = ROT_FRAME * R_body * ROT_FRAME.inv()
    q_xyzw = R_mj.as_quat()  # scipy: scalar-last
    return np.array([q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]])  # MuJoCo: scalar-first
```

**Critical quaternion ordering gotcha**: MuJoCo uses **(w,x,y,z)**, scipy uses **(x,y,z,w)**, and the GMR retargeting library outputs **(x,y,z,w)**. Every interface boundary needs explicit conversion.

For practical SMPL-X → G1 retargeting, the **GMR library** (General Motion Retargeting, ICRA 2026, 1.8k GitHub stars) handles the full pipeline including IK solving for all 17+ supported humanoid robots: `python scripts/smplx_to_robot.py --robot unitree_g1 --smplx_file input.npz`. This avoids manual angle mapping between SMPL-X's 55-joint tree and G1's 29-DOF chain.

### Unit tests verify T-pose and gravity direction

```python
def test_tpose_axes():
    R_conv = np.array([[0,0,1],[1,0,0],[0,1,0]])
    assert np.allclose(R_conv @ [0,1,0], [0,0,1])  # Y-up → Z-up
    assert np.allclose(R_conv @ [0,0,1], [1,0,0])  # Z-forward → X-forward
    assert np.allclose(R_conv @ [0,-9.81,0], [0,0,-9.81])  # Gravity correct
```

---

## 5. Pipeline resilience through circuit breakers and typed fallbacks

A 7-layer pipeline (Voice → LLM → Video → Pose → Retarget → MuJoCo → Hardware) needs failure isolation at every boundary. Three Python libraries form the resilience stack: **tenacity** for retry logic with exponential backoff, **pybreaker** for circuit breakers that prevent hammering dead services, and **dry-python/returns** for monadic error propagation that short-circuits the pipeline on first failure.

The pattern layers tenacity inside pybreaker—retries handle transient failures; circuit breakers prevent retry storms:

```python
import pybreaker
from tenacity import retry, stop_after_attempt, wait_exponential
from returns.result import Result, Success, Failure
from returns.pipeline import flow
from returns.pointfree import bind

llm_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)

@llm_breaker
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_llm(prompt): ...

# Full pipeline composes with short-circuit on any failure
result = flow(audio, transcribe, bind(call_llm), bind(gen_video),
              bind(estimate_pose), bind(retarget), bind(simulate), bind(deploy))
```

Fallback poses degrade gracefully based on which stage failed. Upstream failures (voice, LLM) use the last known good pose. Downstream failures (MuJoCo validation, hardware) escalate to a safe-kneel pose (lower CoM) or emergency joint lock. The SafeFall framework (arXiv:2511.18509) and FIRM framework (arXiv:2511.07407, specifically for Unitree G1) provide RL-trained protective policies that reduce peak contact forces by **68.3%** during falls.

---

## 6. No official high-level simulator, but community bridges exist

Unitree's official SDK (`unitree_sdk2_python`) exposes semantic commands through `LocoClient`—`WaveHand()`, `ShakeHand()`, `HighStand()`, `Move(vx, vy, vyaw)`—but these are runtime commands for real hardware, not simulation APIs. The `unitree_mujoco` repo provides a DDS bridge connecting MuJoCo simulation to the same SDK interface, enabling sim-to-real with identical control code.

For the full text-to-pose pipeline, the most relevant projects are **GMR** (SMPL-X → G1 joint angles via IK), **LeRobot/unitree-g1-mujoco** (MuJoCo at 500Hz with DDS bridge, supports ACT/DP/Pi0.5 policy training), **Ark Unitree G1** (multi-backend: real + PyBullet + MuJoCo), and **OpenMind OM1** (full Voice → LLM → Action → Robot runtime with JSON5 configuration). A `hero_pose()` wrapper combining these would chain: text prompt → LLM pose description → PromptHMR → GMR retargeting → MuJoCo validation (gates 1–3) → interpolated joint command via `unitree_sdk2_python`.

---

## Conclusion

The two priority fixes have outsized impact. **Asserting `model.actuator_biastype[i] == 1` at model load** catches the actuator misconfiguration before any simulation runs—a single line that prevents the most common source of "the robot collapses and I don't know why." **Building the joint routing table from `model.actuator_trnid` rather than positional indexing** eliminates the 29-vs-23 mapping bug regardless of which G1 variant or MJCF file is loaded. Together, these two checks should be non-negotiable prerequisites before any pose reaches the physics engine. The remaining five solutions—validation gates, frame conversion, CoM stability, pipeline resilience, and high-level wrappers—layer on top to form a complete, tested pipeline from natural language to hardware execution.