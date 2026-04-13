"""Velocity-clamp all pkl files in kim_workspace/movements/ for hardware safety."""
import pickle
import numpy as np
import os

PKL_FPS = 30.0
MAX_VEL = 0.5          # rad/s — conservative hardware limit
MAX_DELTA = MAX_VEL / PKL_FPS  # 0.0167 rad/frame


def clamp_numpy(joints):
    """Upsample frames so no joint moves faster than MAX_VEL rad/s.
    Uses pure numpy interpolation — no Python loops over frames.
    """
    N, D = joints.shape
    # Find worst-case velocity ratio across all joints and all transitions
    deltas = np.abs(np.diff(joints, axis=0))        # (N-1, 35)
    max_delta_per_gap = deltas.max(axis=1)           # (N-1,)
    # How many sub-steps does each gap need?
    steps_needed = np.ceil(max_delta_per_gap / MAX_DELTA).astype(int)
    steps_needed = np.maximum(steps_needed, 1)
    # Total output frames
    total = int(steps_needed.sum()) + 1

    # Build output via np.interp over a virtual time axis
    # Original keyframe times
    t_key = np.concatenate([[0], np.cumsum(steps_needed)])  # (N,)
    t_out = np.arange(total, dtype=float)                    # dense grid

    out = np.empty((total, D), dtype=np.float32)
    for j in range(D):
        out[:, j] = np.interp(t_out, t_key, joints[:, j])
    return out


movements = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "kim_workspace", "movements")

for fname in sorted(os.listdir(movements)):
    if not fname.endswith(".pkl"):
        continue
    path = os.path.join(movements, fname)
    with open(path, "rb") as f:
        data = pickle.load(f)

    joints = np.array(data["joint_angles"], dtype=np.float32)
    before = float(np.max(np.abs(np.diff(joints, axis=0)))) * PKL_FPS

    clamped = clamp_numpy(joints)
    after = float(np.max(np.abs(np.diff(clamped, axis=0)))) * PKL_FPS

    data["joint_angles"] = clamped
    with open(path, "wb") as f:
        pickle.dump(data, f)

    print(f"{fname:<45}  {len(joints):>3} -> {len(clamped):>4} frames  "
          f"{before:5.1f} -> {after:.2f} rad/s")
