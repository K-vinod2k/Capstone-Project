"""
hero_pose.py — Mascot Unitree Hero Pose Definitions & Animations

All angles are in radians. The G1 robot has 29 DOF.
We focus on upper-body (arms, shoulders, waist) for expression,
while legs are stabilized separately by the PD controller in server.py.

Positive shoulder_pitch = arm sweeps backward
Negative shoulder_pitch = arm sweeps forward
Positive shoulder_roll  = arm moves outward (abduction)
Negative shoulder_roll  = arm moves inward (adduction)
Positive elbow          = elbow bends (flexion)
"""


# ─── CORE STATIC POSES ─────────────────────────────────────────────────────

DEFAULT_POSE = {
    "left_shoulder_pitch_joint": 0.0,
    "left_shoulder_roll_joint": 0.0,
    "left_shoulder_yaw_joint": 0.0,
    "left_elbow_joint": 0.0,
    "right_shoulder_pitch_joint": 0.0,
    "right_shoulder_roll_joint": 0.0,
    "right_shoulder_yaw_joint": 0.0,
    "right_elbow_joint": 0.0,
}

HERO_POSE = {
    "left_shoulder_pitch_joint": 0.2,
    "left_shoulder_roll_joint": 1.5,
    "left_shoulder_yaw_joint": 0.0,
    "left_elbow_joint": 1.0,
    "right_shoulder_pitch_joint": 0.2,
    "right_shoulder_roll_joint": -1.5,
    "right_shoulder_yaw_joint": 0.0,
    "right_elbow_joint": 1.0,
}

CROUCH_POSE = {
    "left_shoulder_pitch_joint": 1.5,
    "left_shoulder_roll_joint": 0.5,
    "right_shoulder_pitch_joint": 1.5,
    "right_shoulder_roll_joint": -0.5,
    "left_knee_joint": 1.5,
    "right_knee_joint": 1.5,
    "left_hip_pitch_joint": -1.0,
    "right_hip_pitch_joint": -1.0,
}

# PRO-LEAGUE DYNAMIC PHYSICS: Stable athletic stance
STABLE_BALANCE_POSE = {
    # "Z-fold" stance: ankle→knee→hip pitch form a balanced chain so the
    # torso CoM projects over the mid-foot, not behind the heels.
    # hip_pitch=-0.3 leans torso forward; knee=+0.6 provides the bend;
    # ankle=-0.3 tilts the shin forward. All three reciprocal angles keep
    # the CoM inside the support polygon.
    "left_hip_pitch_joint":    -0.3,
    "right_hip_pitch_joint":   -0.3,
    "left_knee_joint":          0.6,
    "right_knee_joint":         0.6,
    "left_ankle_pitch_joint":  -0.3,
    "right_ankle_pitch_joint": -0.3,
    "left_hip_roll_joint":      0.0,
    "right_hip_roll_joint":     0.0,
    "left_hip_yaw_joint":       0.0,
    "right_hip_yaw_joint":      0.0,
    "left_ankle_roll_joint":    0.0,
    "right_ankle_roll_joint":   0.0,
}

# ─── JOINT CATEGORIES ──────────────────────────────────────────────────────

LEG_JOINTS = [
    "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
    "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
    "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
    "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint"
]

UPPER_BODY_JOINTS = [
    "waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint",
    "left_shoulder_pitch_joint", "left_shoulder_roll_joint", "left_shoulder_yaw_joint",
    "left_elbow_joint", "left_wrist_roll_joint", "left_wrist_pitch_joint", "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint", "right_shoulder_roll_joint", "right_shoulder_yaw_joint",
    "right_elbow_joint", "right_wrist_roll_joint", "right_wrist_pitch_joint", "right_wrist_yaw_joint"
]

# ─── ANIMATION SYSTEM ──────────────────────────────────────────────────────

def lerp_pose(pose_a: dict, pose_b: dict, t: float) -> dict:
    """Linear interpolation between two pose dicts. t in [0, 1]."""
    all_joints = set(pose_a.keys()) | set(pose_b.keys())
    result = {}
    for j in all_joints:
        a = pose_a.get(j, 0.0)
        b = pose_b.get(j, 0.0)
        result[j] = a + (b - a) * t
    return result


def ease_in_out(t: float) -> float:
    """Smooth cubic ease-in-out curve for natural motion."""
    return t * t * (3.0 - 2.0 * t)


def animate(keyframes: list, fps: int = 10) -> list:
    """
    Build a smooth trajectory from a list of (pose_dict, duration_seconds) tuples.
    Uses ease-in-out smoothing between each keyframe.
    Returns a flat list of pose dicts sampled at `fps`.
    """
    trajectory = []
    for i in range(len(keyframes) - 1):
        pose_start, dur = keyframes[i]
        pose_end, _    = keyframes[i + 1]
        num_frames = max(1, int(dur * fps))
        for f in range(num_frames):
            raw_t = f / num_frames
            smooth_t = ease_in_out(raw_t)
            trajectory.append(lerp_pose(pose_start, pose_end, smooth_t))
    # Hold the final pose for 0.5s
    final_pose = keyframes[-1][0]
    for _ in range(int(fps * 0.5)):
        trajectory.append(final_pose)
    return trajectory


# ─── HERO-SPECIFIC ANIMATIONS ─────────────────────────────────────────────


def animation_spider_man_web_shoot() -> list:
    """
    Spider-Man web-shooting sequence:
    1. Crouch anticipation (shift weight)
    2. Right arm thrusts forward, wrist cocked
    3. Wrist snaps → web fires
    4. Hold web-shoot pose
    5. Return to ready stance
    """
    ready = {**DEFAULT_POSE, "waist_pitch_joint": -0.1}

    anticipate = {
        "right_shoulder_pitch_joint": 0.4,
        "right_shoulder_roll_joint": -0.2,
        "right_elbow_joint": 1.4,
        "right_wrist_pitch_joint": 0.6,
        "left_shoulder_pitch_joint": 0.3,
        "left_elbow_joint": 0.8,
        "waist_yaw_joint": -0.2,
        "waist_pitch_joint": -0.15,
    }

    thrust = {
        "right_shoulder_pitch_joint": -1.3,
        "right_shoulder_roll_joint": -0.15,
        "right_elbow_joint": 0.4,
        "right_wrist_pitch_joint": -1.0,  # Wrist cocked back
        "left_shoulder_pitch_joint": 0.5,
        "left_elbow_joint": 1.3,
        "waist_yaw_joint": -0.35,
        "waist_pitch_joint": -0.2,
    }

    fire = {
        "right_shoulder_pitch_joint": -1.5,
        "right_shoulder_roll_joint": -0.1,
        "right_elbow_joint": 0.2,
        "right_wrist_pitch_joint": -0.4,  # Wrist snaps → THWIP!
        "right_wrist_yaw_joint": -0.3,
        "left_shoulder_pitch_joint": 0.6,
        "left_elbow_joint": 1.5,
        "waist_yaw_joint": -0.4,
        "waist_pitch_joint": -0.25,
    }

    hold = {**fire}  # Hold the fired position

    return animate([
        (ready,       0.3),
        (anticipate,  0.25),
        (thrust,      0.2),
        (fire,        0.1),   # Snap!
        (hold,        0.8),   # Hold the web-shoot pose
        (ready,       0.4),
    ])


def animation_spider_man_landing() -> list:
    """
    Spider-Man/superhero landing pose (three-point landing):
    1. Drop into crouch
    2. Right hand touches ground
    3. Right knee forward, left leg extended
    4. Torso leans forward
    5. Hold iconic landing pose
    6. Rise gracefully

    NOTE: Robot safety constraints - keeps center of mass balanced
    """
    neutral = {**DEFAULT_POSE}

    crouch_prep = {
        "left_hip_pitch_joint": -1.0,    # Left leg prepares
        "left_knee_joint": 1.2,
        "right_hip_pitch_joint": -0.8,   # Right leg prepares
        "right_knee_joint": 1.0,
        "waist_pitch_joint": -0.3,      # Forward lean start
    }

    landing_pose = {
        # Lower body - shallowed crouch to keep pelvis above 0.4m ZMP threshold
        "left_hip_pitch_joint": -0.9,    # Reduced from -1.2
        "left_knee_joint": 1.3,          # Reduced from 1.8: deep knee was dropping pelvis to 0.378m
        "left_ankle_pitch_joint": -0.5,  # Reduced from -0.8
        "right_hip_pitch_joint": -0.6,
        "right_knee_joint": 0.8,
        "right_ankle_pitch_joint": -0.4,

        # Upper body - iconic landing
        "left_shoulder_pitch_joint": -1.0,
        "left_shoulder_roll_joint": 0.3,
        "left_elbow_joint": 1.2,
        "right_shoulder_pitch_joint": 0.5,
        "right_elbow_joint": 0.8,

        # Torso
        "waist_pitch_joint": -0.4,      # Reduced from -0.8: less forward lean
        "waist_yaw_joint": -0.2,
    }

    rise = {
        "left_hip_pitch_joint": -0.8,   # Start rising
        "left_knee_joint": 1.4,
        "right_hip_pitch_joint": -0.8,
        "right_knee_joint": 1.2,
        "waist_pitch_joint": -0.4,
    }

    return animate([
        (neutral,       0.3),   # Starting stance
        (crouch_prep,   0.4),   # Prepare for landing
        (landing_pose,  0.2),   # Land with impact
        (landing_pose,  1.0),   # Hold iconic pose
        (rise,          0.5),   # Rise up
        (neutral,      0.4),   # Return to neutral
    ])


def animation_spider_man_crawl() -> list:
    """
    Spider-Man wall-crawl perch pose extracted from reference image.

    Image analysis:
      - Both arms nearly horizontal, reaching forward — shoulder_pitch ~ -1.5 rad
      - Arms form ~130 degree V-spread — shoulder_roll ~ ±1.4 rad (max abduction)
      - Palms face flat down (gripping surface) — shoulder_yaw ~ ±0.8 rad
      - Elbows nearly locked straight — elbow ~ 0.15 rad
      - Torso heavily pitched forward (approximated via hip angle in legs)
    """
    ready = {**DEFAULT_POSE}

    # Exact pose extracted from reference image.
    # NOTE: waist_pitch is passive on 23-DOF hardware (KP=0, cannot actuate).
    # Forward torso lean approximated via max hip_pitch + knee flex.
    perch = {
        # Legs — deepest achievable squat within G1 joint limits
        "left_hip_pitch_joint":    -0.43,  # max hip forward flex
        "right_hip_pitch_joint":   -0.43,
        "left_knee_joint":          1.80,  # deep knee bend (~103 deg)
        "right_knee_joint":         1.80,
        "left_ankle_pitch_joint":  -0.43,  # dorsiflexion to keep shin forward
        "right_ankle_pitch_joint": -0.43,

        # Arms — wide V reaching forward, palms flat down (exact from image)
        "left_shoulder_pitch_joint":  -1.5,   # arm horizontal forward
        "left_shoulder_roll_joint":    1.4,   # max abduction, left V-arm
        "left_shoulder_yaw_joint":     0.8,   # palm faces floor
        "left_elbow_joint":            0.15,  # nearly straight
        "left_wrist_roll_joint":       0.3,

        "right_shoulder_pitch_joint": -1.5,
        "right_shoulder_roll_joint":  -1.4,   # max abduction, right V-arm
        "right_shoulder_yaw_joint":   -0.8,
        "right_elbow_joint":           0.15,
        "right_wrist_roll_joint":     -0.3,

        "waist_yaw_joint":             0.0,
    }

    return animate([
        (ready,   0.4),
        (perch,   0.6),   # drop into deep squat + spread arms
        (perch,   1.5),   # hold
        (ready,   0.5),
    ])


def animation_iron_man_repulsor() -> list:
    """
    Iron Man repulsor charging and firing sequence:
    1. Both fists drop to sides (charging stance)
    2. Right arm raises with intensity
    3. Left arm crosses for stability
    4. Repulsor blast (arm fully extended)
    5. Recoil from blast
    6. Return
    """
    neutral = {**DEFAULT_POSE}

    charge = {
        "right_shoulder_pitch_joint": 0.5,
        "right_shoulder_roll_joint": -0.4,
        "right_elbow_joint": 1.6,
        "right_wrist_pitch_joint": 0.5,
        "left_shoulder_pitch_joint": 0.4,
        "left_shoulder_roll_joint": 0.3,
        "left_elbow_joint": 1.4,
        "waist_pitch_joint": -0.05,
    }

    aim = {
        "right_shoulder_pitch_joint": -1.2,
        "right_shoulder_roll_joint": -0.2,
        "right_elbow_joint": 0.3,
        "right_wrist_pitch_joint": 0.1,
        "left_shoulder_pitch_joint": 0.3,
        "left_elbow_joint": 0.7,
        "waist_pitch_joint": -0.1,
        "waist_yaw_joint": -0.15,
    }

    blast = {
        "right_shoulder_pitch_joint": -1.55,  # Full extension
        "right_shoulder_roll_joint": -0.1,
        "right_elbow_joint": 0.05,
        "right_wrist_pitch_joint": -0.15,
        "left_shoulder_pitch_joint": 0.25,
        "left_elbow_joint": 0.6,
        "waist_pitch_joint": -0.12,
        "waist_yaw_joint": -0.2,
    }

    recoil = {
        "right_shoulder_pitch_joint": -1.3,
        "right_shoulder_roll_joint": -0.15,
        "right_elbow_joint": 0.25,
        "waist_pitch_joint": 0.05,  # Slightly pushed back
    }

    return animate([
        (neutral, 0.3),
        (charge,  0.4),     # Charging sound... ⚡
        (aim,     0.3),
        (blast,   0.15),    # FIRE!
        (recoil,  0.2),
        (blast,   0.6),     # Hold the blast
        (neutral, 0.5),
    ])


def animation_hulk_smash() -> list:
    """
    Hulk overhead smash:
    1. Arms spread wide (intimidation)
    2. Both arms SLAM overhead
    3. Momentum builds — smash to ground
    4. Hold impact pose
    5. Rise w/ power
    """
    neutral = {**DEFAULT_POSE}

    spread = {
        "left_shoulder_pitch_joint": 0.2,
        "left_shoulder_roll_joint": 1.8,
        "left_elbow_joint": 0.5,
        "right_shoulder_pitch_joint": 0.2,
        "right_shoulder_roll_joint": -1.8,
        "right_elbow_joint": 0.5,
        "waist_pitch_joint": 0.1,
    }

    overhead = {
        "left_shoulder_pitch_joint": -0.7,   # Bilateral cap: -1.0+ pushes CoM past ZMP on G1
        "left_shoulder_roll_joint": 0.3,
        "left_elbow_joint": 0.3,
        "right_shoulder_pitch_joint": -0.7,
        "right_shoulder_roll_joint": -0.3,
        "right_elbow_joint": 0.3,
        "waist_pitch_joint": 0.35,           # Backward lean to counterbalance
    }

    smash = {
        "left_shoulder_pitch_joint": 0.9,
        "left_shoulder_roll_joint": 0.2,
        "left_elbow_joint": 0.6,
        "right_shoulder_pitch_joint": 0.9,
        "right_shoulder_roll_joint": -0.2,
        "right_elbow_joint": 0.6,
        "waist_pitch_joint": -0.2,  # Reduced: -0.5 caused CoM past ZMP
    }

    impact = {**smash, "waist_pitch_joint": -0.25}  # Reduced from -0.6

    return animate([
        (neutral,  0.3),
        (spread,   0.4),     # HULK SPREAD!
        (overhead, 0.6),     # Arms go UP (slower for balance)
        (smash,    0.5),     # SMASH! — slowed from 0.12s to reduce angular momentum
        (impact,   0.4),
        (impact,   0.9),     # Hold the ground impact
        (spread,   0.4),     # Rise again
        (neutral,  0.4),
    ])


def animation_captain_america_shield() -> list:
    """
    Captain America shield throw:
    1. Plant feet — combat stance
    2. Right arm draws back (wind-up)
    3. Body twists for power
    4. RELEASE — arm sweeps across
    5. Follow-through
    6. Shield-block guard stance
    """
    neutral = {**DEFAULT_POSE}

    stance = {
        "left_shoulder_pitch_joint": -0.3,
        "left_shoulder_roll_joint": 0.9,
        "left_elbow_joint": 1.1,
        "right_shoulder_pitch_joint": 0.2,
        "right_shoulder_roll_joint": -0.3,
        "right_elbow_joint": 0.8,
        "waist_yaw_joint": 0.3,
    }

    windup = {
        "right_shoulder_pitch_joint": 0.5,
        "right_shoulder_roll_joint": -1.2,  # Arm pulled far back
        "right_shoulder_yaw_joint": -0.5,
        "right_elbow_joint": 1.2,
        "left_shoulder_pitch_joint": -0.5,
        "left_shoulder_roll_joint": 0.6,
        "left_elbow_joint": 0.8,
        "waist_yaw_joint": 0.6,  # Body twisted
        "waist_pitch_joint": -0.1,
    }

    release = {
        "right_shoulder_pitch_joint": -1.4,  # Arm sweeps hard forward
        "right_shoulder_roll_joint": -0.1,
        "right_shoulder_yaw_joint": 0.4,
        "right_elbow_joint": 0.15,
        "left_shoulder_pitch_joint": -0.2,
        "left_shoulder_roll_joint": 0.4,
        "left_elbow_joint": 0.5,
        "waist_yaw_joint": -0.4,  # Counter-twist on throw
        "waist_pitch_joint": -0.15,
    }

    followthrough = {
        "right_shoulder_pitch_joint": -0.8,
        "right_shoulder_roll_joint": 0.3,
        "right_elbow_joint": 0.4,
        "left_shoulder_pitch_joint": -0.3,
        "left_shoulder_roll_joint": 0.8,
        "left_elbow_joint": 1.0,
        "waist_yaw_joint": -0.2,
    }

    guard = {
        "left_shoulder_pitch_joint": -1.1,
        "left_shoulder_roll_joint": 0.9,
        "left_elbow_joint": 1.3,
        "right_shoulder_pitch_joint": 0.3,
        "right_elbow_joint": 0.7,
        "waist_yaw_joint": 0.3,
    }

    return animate([
        (neutral,       0.3),
        (stance,        0.35),
        (windup,        0.4),
        (release,       0.1),   # THROW! (very fast)
        (followthrough, 0.25),
        (guard,         0.5),   # Hold guard
        (neutral,       0.4),
    ])


def animation_thor_lightning() -> list:
    """
    Thor lightning summon:
    1. Mjolnir held up — calling the storm
    2. Right arm fully extended overhead
    3. Lightning arcing (trembling emphasis)
    4. Lightning strikes — dramatic pause
    5. Both arms spread in majesty
    """
    neutral = {**DEFAULT_POSE}

    raise_hammer = {
        "right_shoulder_pitch_joint": -1.0,  # Capped to keep CoM stable
        "right_shoulder_roll_joint": -0.15,
        "right_elbow_joint": 0.3,
        "right_wrist_pitch_joint": 0.2,
        "left_shoulder_pitch_joint": 0.3,
        "left_shoulder_roll_joint": 0.4,
        "left_elbow_joint": 0.6,
        "waist_pitch_joint": 0.2,            # Lean back to counterbalance single raised arm
        "waist_yaw_joint": 0.1,
    }

    apex = {
        "right_shoulder_pitch_joint": -1.0,  # Single raised arm — manageable with waist lean
        "right_shoulder_roll_joint": -0.1,
        "right_elbow_joint": 0.05,
        "left_shoulder_pitch_joint": 0.2,    # Left arm stays back to counterbalance
        "left_shoulder_roll_joint": 0.5,
        "left_elbow_joint": 0.4,
        "waist_pitch_joint": 0.25,           # Back lean to counterbalance single raised arm
    }

    # Slight tremble for lightning effect (two oscillations)
    tremble_a = {**apex, "right_shoulder_roll_joint": 0.05, "right_wrist_yaw_joint": 0.2}
    tremble_b = {**apex, "right_shoulder_roll_joint": -0.1, "right_wrist_yaw_joint": -0.2}

    strike = {
        "right_shoulder_pitch_joint": -1.0,
        "right_shoulder_roll_joint": -0.1,
        "right_elbow_joint": 0.05,
        "left_shoulder_pitch_joint": 0.2,
        "left_shoulder_roll_joint": 0.6,
        "left_elbow_joint": 0.5,
        "waist_pitch_joint": 0.25,
    }

    majesty = {
        "left_shoulder_pitch_joint": -1.0,
        "left_shoulder_roll_joint": 1.4,
        "left_elbow_joint": 0.5,
        "right_shoulder_pitch_joint": -1.0,
        "right_shoulder_roll_joint": -1.4,
        "right_elbow_joint": 0.5,
        "waist_pitch_joint": 0.1,
    }

    return animate([
        (neutral,    0.3),
        (raise_hammer, 0.5),
        (apex,       0.5),     # Slower raise for balance
        (tremble_a,  0.2),     # Slowed from 0.12s
        (tremble_b,  0.2),
        (tremble_a,  0.2),
        (strike,     0.3),     # Slowed from 0.08s
        (strike,     0.7),     # Hold the power
        (majesty,    0.5),
        (neutral,    0.5),
    ])


def animation_wolverine_claws() -> list:
    """Wolverine claw reveal and slash."""
    neutral = {**DEFAULT_POSE}

    tense = {
        "right_shoulder_pitch_joint": 0.1,
        "right_shoulder_roll_joint": -0.3,
        "right_elbow_joint": 1.3,
        "left_shoulder_pitch_joint": 0.1,
        "left_shoulder_roll_joint": 0.3,
        "left_elbow_joint": 1.3,
        "waist_pitch_joint": -0.1,
    }

    claws_out = {
        "right_shoulder_pitch_joint": -0.3,
        "right_shoulder_roll_joint": -0.5,
        "right_elbow_joint": 1.0,
        "right_wrist_yaw_joint": 0.4,
        "left_shoulder_pitch_joint": -0.3,
        "left_shoulder_roll_joint": 0.5,
        "left_elbow_joint": 1.0,
        "left_wrist_yaw_joint": -0.4,
        "waist_pitch_joint": -0.15,
    }

    slash = {
        "right_shoulder_pitch_joint": -1.3,
        "right_shoulder_roll_joint": 0.2,
        "right_elbow_joint": 0.4,
        "right_wrist_yaw_joint": 0.6,
        "left_shoulder_pitch_joint": 0.5,
        "left_shoulder_roll_joint": 0.8,
        "left_elbow_joint": 0.8,
        "waist_yaw_joint": -0.5,
        "waist_pitch_joint": -0.2,
    }

    return animate([
        (neutral,   0.3),
        (tense,     0.35),
        (claws_out, 0.3),    # *SNIKT*
        (claws_out, 0.5),    # Hold menacingly
        (slash,     0.15),   # Slash attack
        (claws_out, 0.4),    # Recover
        (neutral,   0.4),
    ])


def animation_wave() -> list:
    """Friendly wave (right arm, two oscillations)."""
    neutral = {**DEFAULT_POSE}

    up = {
        "right_shoulder_pitch_joint": -1.8,
        "right_shoulder_roll_joint": -0.7,
        "right_elbow_joint": 1.0,
        "left_shoulder_pitch_joint": 0.1,
        "left_elbow_joint": 0.2,
    }

    wave_l = {**up, "right_wrist_yaw_joint": -0.4, "right_wrist_pitch_joint": 0.3}
    wave_r = {**up, "right_wrist_yaw_joint": 0.4, "right_wrist_pitch_joint": -0.3}

    return animate([
        (neutral, 0.3),
        (up,      0.35),
        (wave_l,  0.2),
        (wave_r,  0.2),
        (wave_l,  0.2),
        (wave_r,  0.2),
        (wave_l,  0.2),
        (up,      0.2),
        (neutral, 0.4),
    ])


def animation_flex() -> list:
    """Muscle flex — both arms curl up."""
    neutral = {**DEFAULT_POSE}

    spread = {
        "left_shoulder_pitch_joint": -0.1,
        "left_shoulder_roll_joint": 1.6,
        "left_elbow_joint": 0.2,
        "right_shoulder_pitch_joint": -0.1,
        "right_shoulder_roll_joint": -1.6,
        "right_elbow_joint": 0.2,
    }

    flex = {
        "left_shoulder_pitch_joint": -1.0,
        "left_shoulder_roll_joint": 1.3,
        "left_elbow_joint": 1.6,
        "right_shoulder_pitch_joint": -1.0,
        "right_shoulder_roll_joint": -1.3,
        "right_elbow_joint": 1.6,
        "waist_pitch_joint": -0.15,
    }

    return animate([
        (neutral, 0.3),
        (spread,  0.4),
        (flex,    0.35),
        (flex,    0.8),
        (neutral, 0.5),
    ])


def animation_punch() -> list:
    """Power punch — right jab."""
    neutral = {**DEFAULT_POSE}

    guard = {
        "right_shoulder_pitch_joint": 0.2,
        "right_shoulder_roll_joint": -0.3,
        "right_elbow_joint": 1.4,
        "left_shoulder_pitch_joint": 0.2,
        "left_shoulder_roll_joint": 0.4,
        "left_elbow_joint": 1.2,
        "waist_pitch_joint": -0.1,
    }

    extend = {
        "right_shoulder_pitch_joint": -1.5,
        "right_shoulder_roll_joint": -0.05,
        "right_elbow_joint": 0.05,
        "left_shoulder_pitch_joint": 0.3,
        "left_shoulder_roll_joint": 0.3,
        "left_elbow_joint": 1.5,
        "waist_yaw_joint": -0.45,
        "waist_pitch_joint": -0.18,
    }

    return animate([
        (neutral, 0.25),
        (guard,   0.3),
        (extend,  0.1),   # JAB! (fast)
        (extend,  0.4),
        (guard,   0.25),
        (neutral, 0.4),
    ])


# ─── LLM-POWERED POSE ANALYSIS ──────────────────────────────────────

def analyze_pose_with_llm(gesture_desc: str, hero_name: str) -> str:
    """
    Use LLM to analyze the gesture description and recommend the best animation.
    Returns the animation function name.
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        return _fallback_gesture_mapping(gesture_desc)

    prompt = f"""Analyze this gesture description and select the most appropriate animation.

Hero: {hero_name}
Gesture Description: "{gesture_desc}"

Available animations:
- iron_man_repulsor (repulsor blast, palm forward)
- spider_man_web_shoot (web shooting, wrist flick)
- spider_man_landing (superhero landing, crouch pose)
- hulk_smash (overhead smash, ground pound)
- captain_america_shield (shield throw/block)
- thor_lightning (hammer raise, lightning summon)
- wolverine_claws (claw slash, snikt)
- wave (friendly wave)
- flex (muscle flex)
- punch (power punch)

Return ONLY the animation function name that best matches. No explanation."""

    try:
        from huggingface_hub import InferenceClient
        hf_client = InferenceClient(model="Qwen/Qwen2.5-72B-Instruct", token=hf_token)
        response = hf_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.2,
        )
        animation_name = response.choices[0].message.content.strip().replace("animation_", "").lower()

        valid_animations = {
            "iron_man_repulsor", "spider_man_web_shoot", "spider_man_landing",
            "hulk_smash", "captain_america_shield", "thor_lightning", "wolverine_claws",
            "wave", "flex", "punch"
        }

        if animation_name in valid_animations:
            print(f"🤖 LLM selected animation: {animation_name}")
            return animation_name
        else:
            print(f"⚠️ LLM returned invalid animation: '{animation_name}', using fallback")
            return _fallback_gesture_mapping(gesture_desc)

    except Exception as e:
        print(f"⚠️ LLM analysis failed: {e}, using fallback")
        return _fallback_gesture_mapping(gesture_desc)

def _fallback_gesture_mapping(gesture_desc: str) -> str:
    """Fallback keyword-based mapping when LLM is unavailable"""
    desc = gesture_desc.lower()

    if any(w in desc for w in ["repulsor", "blast", "palm", "iron man", "ironman"]):
        return "iron_man_repulsor"
    elif any(w in desc for w in ["web", "shoot", "thwip"]):
        return "spider_man_web_shoot"
    elif any(w in desc for w in ["spider", "spider-man", "spiderman", "landing", "crouch", "superhero landing", "three-point"]):
        return "spider_man_landing"
    elif any(w in desc for w in ["smash", "slam", "overhead", "hulk", "ground pound"]):
        return "hulk_smash"
    elif any(w in desc for w in ["shield", "throw", "captain", "vibranium", "cap "]):
        return "captain_america_shield"
    elif any(w in desc for w in ["lightning", "thunder", "thor", "hammer", "mjolnir", "storm"]):
        return "thor_lightning"
    elif any(w in desc for w in ["claw", "slash", "wolverine", "snikt", "berserker"]):
        return "wolverine_claws"
    elif any(w in desc for w in ["wave", "greet", "hello", "hi ", "friendly"]):
        return "wave"
    elif any(w in desc for w in ["flex", "muscle", "bicep", "strong", "power pose"]):
        return "flex"
    elif any(w in desc for w in ["punch", "strike", "jab", "hit", "fist"]):
        return "punch"
    else:
        return "iron_man_repulsor"  # default showpiece


# ─── ENHANCED GESTURE → TRAJECTORY DISPATCHER ──────────────────────────────────────

def gesture_to_trajectory(gesture_desc: str, hero_name: str = "Generic Hero") -> list:
    """
    Enhanced gesture mapping using LLM analysis when available.
    Maps a gesture description to the most appropriate smooth animated trajectory.
    """
    # Use LLM to select the best animation
    animation_name = analyze_pose_with_llm(gesture_desc, hero_name)

    # Dispatch to the appropriate animation function
    animation_map = {
        "iron_man_repulsor": animation_iron_man_repulsor,
        "spider_man_web_shoot": animation_spider_man_web_shoot,
        "spider_man_landing": animation_spider_man_landing,
        "hulk_smash": animation_hulk_smash,
        "captain_america_shield": animation_captain_america_shield,
        "thor_lightning": animation_thor_lightning,
        "wolverine_claws": animation_wolverine_claws,
        "wave": animation_wave,
        "flex": animation_flex,
        "punch": animation_punch
    }

    if animation_name in animation_map:
        print(f"🎬 Playing {animation_name.replace('_', ' ')} animation for {hero_name}")
        return animation_map[animation_name]()
    else:
        print(f"⚠️ Animation '{animation_name}' not found, using default")
        return animation_iron_man_repulsor()
