"""pkl_29_to_23.py - Convert raw video2robot 29-DOF G1 PKLs into 23-DOF hero library format.

Authoritative spec: Unitree G1 developer docs joint-index tables mirrored in
G1_23DOF_Specs/g1_joint_index_dds.md and documented on DeepWiki
(https://deepwiki.com/unitreerobotics/unitree_ros2/4.2.4-g1-low-level-control).

The DDS wire format (unitree_hg::LowCmd / LowState) is ALWAYS a 29-slot
motor_cmd array. The SKU difference is which slots are real motors vs.
empty/ignored, and how slots 4/5/10/11 are interpreted via mode_pr:
    mode_pr=0 (PR): slots 4,5,10,11 = ANKLE_PITCH / ANKLE_ROLL
    mode_pr=1 (AB): slots 4,5,10,11 = ANKLE_B / ANKLE_A
This is one pair of physical parallel-linkage ankle motors, just re-parameterized.

Source (29-DOF, matches scene.xml actuator order and the G1 developer table):
    0-11  legs (hip_p/r/y, knee, ankle_p, ankle_r x 2)
    12    WAIST_YAW
    13    WAIST_ROLL     <- DROPPED (no motor on 23-DOF waist-locked SKU)
    14    WAIST_PITCH    <- DROPPED
    15-21 L arm: shoulder_p/r/y, elbow, wrist_roll, wrist_pitch, wrist_yaw
    22-28 R arm: same 7 DOF
    The 29-DOF arm has 7 DOF; 23-DOF has only 5 DOF per arm.

Target (hero library format consumed by clamp_pkls.py, render_animations.py,
deploy_real.py, and deploy_protomotions.py):
    35-wide joint_angles array in 23-DOF IDL order (g1_joint_index_dds.md):
        [0-11]  legs - pass through
        [12]    TORSO (waist_yaw)
        [13-17] left arm (shoulder_pitch/roll/yaw, elbow_pitch, elbow_roll == 29-DOF wrist_roll)
        [18-22] right arm (same 5 DOF)
        [23-34] unused on 23-DOF hardware - filled with zeros

Dropped joints (no hardware counterpart on 23-DOF G1):
    waist_roll (src 13), waist_pitch (src 14),
    L_wrist_pitch (src 20), L_wrist_yaw (src 21),
    R_wrist_pitch (src 27), R_wrist_yaw (src 28).

Semantic collapse: 29-DOF "wrist_roll" (src 19, 26) physically IS the 23-DOF
"elbow_roll" motor (tgt 17, 22). One DOF, two names across SKUs.

Note: on 29-DOF arm-SDK coexistence mode (rt/arm_sdk topic), the weight-blend
bit is at motor_cmd[29].q. That is a different code path from this full-body
remap and is not exercised by pkl_29_to_23.

Usage:
    python vinod_workspace/pkl_29_to_23.py \
        --input  "Pkl files/2026-03-12_07-17-04.pkl" \
        --output kim_workspace/movements/candidate_17-04_kinematics.pkl

    python vinod_workspace/pkl_29_to_23.py --preview-all
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENE_XML = REPO_ROOT / "kim_workspace/hardware_deployment/unitree_mujoco/unitree_robots/g1/scene.xml"

# Target hero-library width (matches existing kim_workspace/movements/*.pkl).
TARGET_WIDTH = 35

# Map target IDL index -> source 29-DOF index (None = zero-fill).
# Derived from scene.xml actuator order and g1_joint_index_dds.md 23-DOF table.
IDL_TO_SRC: dict[int, Optional[int]] = {
    # Legs pass through (same order in both layouts).
    **{i: i for i in range(12)},
    12: 12,  # torso / waist_yaw
    13: 15,  # L_shoulder_pitch
    14: 16,  # L_shoulder_roll
    15: 17,  # L_shoulder_yaw
    16: 18,  # L_elbow_pitch
    17: 19,  # L_elbow_roll  (== L_wrist_roll on 29-DOF source)
    18: 22,  # R_shoulder_pitch
    19: 23,  # R_shoulder_roll
    20: 24,  # R_shoulder_yaw
    21: 25,  # R_elbow_pitch
    22: 26,  # R_elbow_roll  (== R_wrist_roll on 29-DOF source)
    # 23..34 unused on 23-DOF hardware (zero-fill).
}

# Source indices that are dropped (no 23-DOF counterpart).
_DROPPED_SRC_INDICES = (13, 14, 20, 21, 27, 28)


def load_ctrl_limits(scene_xml: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (lo, hi) ctrl ranges indexed by 29-DOF actuator id."""
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(scene_xml))
    if model.nu != 29:
        raise RuntimeError(
            f"Expected 29 actuators in scene.xml, found {model.nu}. "
            "Did scene.xml change?"
        )
    return model.actuator_ctrlrange[:, 0].copy(), model.actuator_ctrlrange[:, 1].copy()


def remap_frames(src: np.ndarray, safety_margin: float = 0.05) -> np.ndarray:
    """Convert (N, 29) source dof_pos to (N, 35) 23-DOF joint_angles.

    Clamps each source channel to its MuJoCo actuator ctrlrange with a small
    safety margin. Unused target columns (23..34) are zero-filled.
    """
    if src.ndim != 2 or src.shape[1] != 29:
        raise ValueError(f"Expected source shape (N, 29), got {src.shape}")

    ctrl_lo, ctrl_hi = load_ctrl_limits(SCENE_XML)
    ctrl_lo = ctrl_lo + safety_margin
    ctrl_hi = ctrl_hi - safety_margin

    src_clamped = np.clip(src, ctrl_lo, ctrl_hi)

    n = src.shape[0]
    out = np.zeros((n, TARGET_WIDTH), dtype=np.float32)
    for idl_idx, src_idx in IDL_TO_SRC.items():
        if src_idx is not None:
            out[:, idl_idx] = src_clamped[:, src_idx].astype(np.float32)
    return out


def summarize_drops(raw: np.ndarray) -> list[tuple[int, str, float]]:
    """Return (src_idx, label, ptp) for each dropped channel whose range > 0.05 rad.

    Useful for reporting gesture signal lost by the 29 -> 23 remap.
    """
    labels = {
        13: "waist_roll",
        14: "waist_pitch",
        20: "L_wrist_pitch",
        21: "L_wrist_yaw",
        27: "R_wrist_pitch",
        28: "R_wrist_yaw",
    }
    out: list[tuple[int, str, float]] = []
    for src_idx in _DROPPED_SRC_INDICES:
        rng = float(np.ptp(raw[:, src_idx]))
        if rng > 0.05:
            out.append((src_idx, labels[src_idx], rng))
    return out


def remap_pkl(input_path: Path, output_path: Path, verbose: bool = True) -> None:
    with input_path.open("rb") as f:
        src_data = pickle.load(f)

    raw = np.asarray(src_data.get("dof_pos", src_data.get("joint_angles")))
    if raw is None:
        raise KeyError(f"{input_path}: no 'dof_pos' or 'joint_angles' key")
    if raw.shape[1] != 29:
        raise ValueError(
            f"{input_path}: expected 29-DOF source, got {raw.shape[1]} columns. "
            "This file may already be remapped to 23-DOF IDL."
        )

    joint_angles = remap_frames(raw)

    out = {
        "joint_angles": joint_angles,
        "fps": float(src_data.get("fps", 30.0)),
        "root_pos": np.asarray(src_data.get("root_pos")) if "root_pos" in src_data else None,
        "root_rot": np.asarray(src_data.get("root_rot")) if "root_rot" in src_data else None,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        pickle.dump(out, f)

    if verbose:
        print(f"  {input_path.name}  ->  {output_path.name}")
        print(f"    frames: {joint_angles.shape[0]}  fps: {out['fps']:.2f}")
        drops = summarize_drops(raw)
        if drops:
            print("    dropped joints with signal > 0.05 rad (lost by 29->23 remap):")
            for src_idx, label, rng in drops:
                print(f"      [src {src_idx}] {label}: {rng:.3f} rad")
        else:
            print("    no significant signal in dropped joints.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", "-i", type=Path, help="Raw 29-DOF PKL to remap")
    parser.add_argument("--output", "-o", type=Path, help="Destination 23-DOF PKL")
    parser.add_argument(
        "--preview-all",
        action="store_true",
        help="Remap every non-remapped .pkl in 'Pkl files/_source_29dof/' into sibling 'Pkl files/_previews_23dof/'",
    )
    args = parser.parse_args()

    if args.preview_all:
        pkl_root = REPO_ROOT / "Pkl files"
        src_dir = pkl_root / "_source_29dof"
        out_dir = pkl_root / "_previews_23dof"
        files = sorted(p for p in src_dir.glob("*.pkl") if "remapped" not in p.name)
        print(f"Remapping {len(files)} raw PKLs -> {out_dir}")
        for src in files:
            remap_pkl(src, out_dir / f"{src.stem}_23dof.pkl")
    else:
        if not args.input or not args.output:
            parser.error("Provide --input and --output, or use --preview-all.")
        remap_pkl(args.input, args.output)


if __name__ == "__main__":
    main()
