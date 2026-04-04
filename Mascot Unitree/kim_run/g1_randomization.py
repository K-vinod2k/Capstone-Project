from isaaclab.managers import ModifierCfg, SceneEntityCfg
from isaaclab.envs import mdp
from isaaclab.utils import configclass

@configclass
class G1RandomizationCfg:
    """Sim-to-Real Domain Randomizations for the Unitree G1."""
    
    # 1. Observation Noise
    # Introduce real-world sensor inaccuracies for the joints and IMU
    add_observation_noise = True
    observation_noise_level = 0.05
    
    # 2. Base Mass Randomization (H4 fix: includes CoM translation)
    # Varies the payload by +/- 1.0kg to account for battery sag or wire weights
    randomize_base_mass = ModifierCfg(
        func=mdp.randomize_rigid_body_mass,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names="trunk"), 
            "mass_distribution": ("uniform", -1.0, 1.0)
        }
    )
    
    randomize_com_offset = ModifierCfg(
        func=mdp.randomize_rigid_body_coms,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names="trunk"),
            "com_distribution": ("uniform", [-0.02, -0.02, -0.02], [0.02, 0.02, 0.02])
        }
    )
    
    # 3. Ground Friction Randomization
    # Prevents overfitting to a specific virtual floor material
    randomize_friction = ModifierCfg(
        func=mdp.randomize_surface_friction,
        params={
            "distribution": ("uniform", 0.5, 1.2)
        }
    )
    
    # 4. Joint Friction and Damping (H3 fix)
    # Models internal gearbox friction for the 35 motors
    randomize_joint_friction = ModifierCfg(
        func=mdp.randomize_joint_parameters,
        params={
            "asset_cfg": SceneEntityCfg("robot", joint_names=".*"),
            "friction_distribution": ("uniform", 0.0, 0.05),
            "damping_distribution": ("uniform", 0.0, 0.1)
        }
    )
    
    # 5. PD Gain Randomization (H5 fix)
    # Limits perfect tracking to account for battery voltage sag and thermal throttling
    randomize_actuator_gains = ModifierCfg(
        func=mdp.randomize_actuator_gains,
        params={
            "asset_cfg": SceneEntityCfg("robot", joint_names=".*"),
            "stiffness_distribution": ("uniform", 0.8, 1.2),  # Kp multiplier
            "damping_distribution": ("uniform", 0.8, 1.2)     # Kd multiplier
        }
    )
    
    # 6. Action Delay (H1 fix)
    # Buffers actions by 1-3 ticks to simulate hardware communication lag
    randomize_action_delay = ModifierCfg(
        func=mdp.randomize_action_delay,
        params={
            "delay_distribution": ("uniform", 1, 3) 
        }
    )
