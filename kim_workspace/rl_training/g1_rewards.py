import torch
from isaaclab.envs import ManagerBasedRLEnv
from isaaclab.managers import SceneEntityCfg

def track_target_pose_exp(
    env: ManagerBasedRLEnv, 
    std: float, 
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Reward for tracking the AI-generated target joint angles using exponential kernel."""
    asset = env.scene[asset_cfg.name]
    
    # Get the target pose sent by the video extractor
    target_angles = env.command_manager.get_command("target_pose")
    
    # Current joint positions
    current_angles = asset.data.joint_pos
    
    # Square error sum across all joints
    error = torch.sum(torch.square(target_angles - current_angles), dim=1)
    
    # Exponential reward (closer to target = higher reward)
    return torch.exp(-error / (std**2))

def penalty_for_falling(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Massive penalty if the robot's Z-height drops signifying a fall."""
    asset = env.scene["robot"]
    
    # Height of the root (pelvis) in world frame
    root_z = asset.data.root_pos_w[:, 2]
    
    # G1 normal standing is ~0.8m. Below 0.4m is considered fallen.
    fell = root_z < 0.4
    
    # Return -100 if fell, 0 otherwise
    return torch.where(fell, torch.tensor(-100.0, device=env.device), torch.tensor(0.0, device=env.device))

def imitation_recovery_reward(env: ManagerBasedRLEnv, std: float) -> torch.Tensor:
    """VLAW Phase 4: Imitation Reward based on matching the Hulk recovery .pkl kinematics."""
    asset = env.scene["robot"]
    
    # Retrieve the synthetic target recovery pose mapped via VLAW Handshake
    try:
        synthetic_recovery_target = env.command_manager.get_command("hulk_recovery_pose")
        current_angles = asset.data.joint_pos
        
        error = torch.sum(torch.square(synthetic_recovery_target - current_angles), dim=1)
        return torch.exp(-error / (std**2)) * 10.0 # High priority objective
    except Exception:
        # If no recovery command is queued, reward is 0
        return torch.zeros(env.num_envs, device=env.device)
