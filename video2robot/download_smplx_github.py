import urllib.request
import os

url = "https://github.com/vchoutas/smplx/raw/master/models/smplx/SMPLX_NEUTRAL.npz"
dest = "/Users/vinodkumar/Desktop/Capstone/video2robot/data/body_models/smplx/SMPLX_NEUTRAL.npz"

print(f"Downloading from {url}...")
try:
    urllib.request.urlretrieve(url, dest)
    size = os.path.getsize(dest)
    print(f"✅ Download complete! Size: {size} bytes")
    if size < 1000000:
        print("⚠️ Warning: File size is unexpectedly small. It might be an LFS pointer.")
except Exception as e:
    print(f"❌ Error downloading file: {e}")
