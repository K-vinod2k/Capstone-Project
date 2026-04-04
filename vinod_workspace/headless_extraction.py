import os
import sys
from pathlib import Path

# Add promptHMR to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "video2robot", "third_party", "PromptHMR", "pipeline")))

try:
    from pipeline import run_pipeline
except ImportError:
    print("WARNING: PromptHMR environment not active. Please run inside the 'phmr' conda env.")

def extract_hulk_kinematics():
    video_path = Path(__file__).parent / "hulk_smash_static.mp4"
    output_pkl = Path(__file__).parent / "hulk_kinematics.pkl"
    
    if not video_path.exists():
        print(f"Error: {video_path} not found.")
        return
        
    print(f"[VLAW Headless] Starting Pose Extraction on {video_path}...")
    
    # Run the PromptHMR pipeline headlessly
    try:
        # Assumes run_pipeline takes video path and outputs to a cache or explicit returned object
        # This will save the `.pkl` internally or we can move it
        result_pkl_path = run_pipeline(str(video_path), output_dir=str(Path(__file__).parent))
        print(f"[VLAW Headless] Success! Kinematics saved to {result_pkl_path}")
    except Exception as e:
        print(f"Extraction failed: {e}")

if __name__ == "__main__":
    extract_hulk_kinematics()
