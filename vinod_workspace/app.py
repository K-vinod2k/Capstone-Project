from flask import Flask, request, jsonify
import argparse
from g1_loco_overlay_functional import *
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
import asyncio
import time

p = argparse.ArgumentParser(description="No-fall G1 controller (rt/arm_sdk overlay).")
p.add_argument("iface", help="network interface, e.g. enp0s31f6 (Linux) or en0") # eth0
args = p.parse_args()

ctrl = G1NoFallController(args.iface)

audio_client = AudioClient()
audio_client.SetTimeout(10.0)
audio_client.Init()
audio_client.SetVolume(100)

app = Flask(__name__)



async def pose_robot(robot, movement):
    if movement:
        robot.play_arm_gesture(movement, flip_r_shoulder_roll=False)

async def move_robot(robot, data):
    
    """
    data (dict)
    args:
    - "robot_instructed_to_move_by_user": bool (True, False) # Python Bool, capitalize True or False | If user instruction has nothing to do with movement, this should be False
    - "direction": string # forward, backward, left, right
    - "velocity": float # range: 0.0 to 0.5
    - "duration": float # range: 0.0 to 5.0


    "fwd": {"vx": v}, 
    "back": {"vx": -v},
    "left": {"vy": v}, 
    "right": {"vy": -v},
    "turn": {"yaw": v}
    """
    if data:
        #robot.walk(data)
        return

async def talk_robot(text):
    if text:
        audio_client.TtsMaker(text, 1)

async def blink_robot(text):
    if text:
        count = len(text.split(" "))
        duration = count * 0.2
        start = time.perf_counter()

        while time.perf_counter() < start + duration:
            audio_client.LedControl(255, 0, 0)
            time.sleep(0.1)
            audio_client.LedControl(0, 0, 0)
            time.sleep(0.1)

@app.route('/process_movement', methods=['POST'])
async def process_movement():
    # 1. Get the JSON data from the request
    data = request.get_json()

    # 2. Basic validation to ensure data exists
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    # 3. Extract the specific fields sent by your script

    pose = data.get('pose')
    if pose:
        pose['joint_angles'] = np.array(pose['joint_angles'])

    text = data.get('text')

    move = data.get('move')

    """
    data: movement pickle JSON (dict)
    pose: pose pickle file (stored as dict, can be None)
    text: the text that the robot should say

    """

    #asyncio.create_task(talk_robot(text))
    #asyncio.create_task(blink_robot(text))
    #asyncio.create_task(pose_robot(ctrl, pose))

    
    result = await asyncio.gather(
        talk_robot(text), #blink_robot(text),
        pose_robot(ctrl, pose)
        move_robot(ctrl, move)
    )
    
    
    """
    try:
        ctrl.play_arm_gesture(movement, flip_r_shoulder_roll=False)
    
    except Exception as e:
        print("Error processing data", e)

    if text:
        audio_client.TtsMaker(text, 1)
    """

    # Example Logic: Just printing the received data to the console
    print(f"Received Text: {text}")
    if pose:
        print(f"Movement Keys: {list(pose.keys())}")
        # If joint_angles were sent, they are now a list
        joint_angles = pose.get('joint_angles', [])
        print(f"Number of joint angle frames: {len(joint_angles)}")

    # 4. Return a response back to the client
    return jsonify({
        "status": "success",
        "message": "Data received successfully",
        "received_text_length": len(text) if text else 0
    }), 200

if __name__ == '__main__':
    # Run the server on localhost:5000

    app.run(host='0.0.0.0', port=5000)