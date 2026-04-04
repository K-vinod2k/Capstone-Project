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
    
    # 2. Base Mass Randomization
    # Varies the payload by +/- 1.0kg to account for battery sag or wire weights
    randomize_base_mass = ModifierCfg(
        func=mdp.randomize_rigid_body_mass,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names="trunk"), 
            "mass_distribution": ("uniform", -1.0, 1.0)
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
