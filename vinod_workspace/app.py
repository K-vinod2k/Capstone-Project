from flask import Flask, request, jsonify
import argparse
from g1_loco_overlay_functional import *

p = argparse.ArgumentParser(description="No-fall G1 controller (rt/arm_sdk overlay).")
p.add_argument("iface", help="network interface, e.g. enp0s31f6 (Linux) or en0")
args = p.parse_args()

ctrl = G1NoFallController(args.iface)

app = Flask(__name__)

@app.route('/process_movement', methods=['POST'])
def process_movement():
    # 1. Get the JSON data from the request
    data = request.get_json()

    # 2. Basic validation to ensure data exists
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    # 3. Extract the specific fields sent by your script
    movement = data.get('movement')
    text = data.get('text')

    """
    data: movement pickle JSON (dict)
    movement: movement pickle file (stored as dict, can be None)
    text: the text that the robot should say

    """

    try:
        ctrl.play_arm_gesture(data, flip_r_shoulder_roll=args.flip_r_shoulder_roll)
    
    except Exception as e:
        print("Error processing data", e)


    # Example Logic: Just printing the received data to the console
    print(f"Received Text: {text}")
    if movement:
        print(f"Movement Keys: {list(movement.keys())}")
        # If joint_angles were sent, they are now a list
        joint_angles = movement.get('joint_angles', [])
        print(f"Number of joint angle frames: {len(joint_angles)}")

    # 4. Return a response back to the client
    return jsonify({
        "status": "success",
        "message": "Data received successfully",
        "received_text_length": len(text) if text else 0
    }), 200

if __name__ == '__main__':
    # Run the server on localhost:5000
    app.run(debug=True)