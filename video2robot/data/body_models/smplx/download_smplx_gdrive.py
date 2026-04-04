import requests
import zipfile
import os
import shutil

def download_file_from_google_drive(id, destination):
    print("Initializing Google Drive Session...")
    URL = "https://docs.google.com/uc?export=download"
    session = requests.Session()
    response = session.get(URL, params={'id': id}, stream=True)
    
    # Check for the virus scan confirmation token 
    token = None
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            token = value
            break
            
    if token:
        params = {'id': id, 'confirm': token}
        response = session.get(URL, params=params, stream=True)

    print("Downloading models_smplx_v1_1.zip...")
    total_size = 0
    with open(destination, "wb") as f:
        for chunk in response.iter_content(32768):
            if chunk: 
                f.write(chunk)
                total_size += len(chunk)
    print(f"✅ Downloaded {total_size} bytes!")

download_file_from_google_drive('1zXQ-A3gN5Fz-_jZq3mI_R46gY4B_O0Vd', 'models_smplx.zip')

print("Extracting...")
with zipfile.ZipFile('models_smplx.zip', 'r') as zip_ref:
    zip_ref.extractall('.')
    
if os.path.exists("models/smplx/SMPLX_NEUTRAL.npz"):
    shutil.copy("models/smplx/SMPLX_NEUTRAL.npz", "SMPLX_NEUTRAL.npz")
    print("✅ Successfully extracted true SMPLX_NEUTRAL.npz!")
