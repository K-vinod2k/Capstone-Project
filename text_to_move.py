from kim_workspace.robot_persona.src import RobotPersona
from kim_workspace.stt.src import STT
import sounddevice as sd
from dotenv import load_dotenv
import os
import subprocess

def pickle_to_movement(path, env_name="unisim"):

    """
    
    Implement function that opens the robot pickle file
    and converts it into robot movement

    Input:
    path: str (directory to movement pickle file)

    """
    # YOUR CODE HERE
    process = f"""conda run -n {env_name} python vinod_workspace/deploy_real.py -- pkl {path} -- iface eth0 -- speed 0.5"""
    subprocess.run(process.split())

    print("[PICKLE TO ROBOT MOVEMENT: TODO]")

if __name__ == "__main__":

    # Input Variables
    persona = "a Superhero"
    movement_directory = './kim_workspace/movements'

    # Models
    load_dotenv()
    HF_TOKEN = os.getenv('HF_TOKEN') # Or use your own huggingface API Key
    persona = RobotPersona(persona, movement_directory)
    stt = STT()
    stream = sd.InputStream(samplerate=stt.SAMPLERATE, 
                        channels=1, 
                        callback=stt.audio_callback)

    with stream:
        stt.process_audio(persona.forward, pickle_to_movement)
