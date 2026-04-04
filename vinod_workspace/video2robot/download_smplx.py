import shutil
from huggingface_hub import hf_hub_download

# Direct download of SMPLX_NEUTRAL.npz
try:
    path = hf_hub_download(repo_id="nbei/smplx_models", filename="smplx/SMPLX_NEUTRAL.npz")
    dest = "/Users/vinodkumar/Desktop/Capstone/video2robot/data/body_models/smplx/SMPLX_NEUTRAL.npz"
    shutil.copy(path, dest)
    print(f"✅ Successfully downloaded SMPLX_NEUTRAL.npz to {dest}")
except Exception as e:
    print(f"Error: {e}")
