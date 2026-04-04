import sys
import json
import base64
import os

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        user_prompt = input_data.get('prompt', '')
        persona_name = input_data.get('persona', 'Generic Robot')
        
        # 1. Persona Engine
        # Try to import local persona_brain if it exists
        response_dict = {
            "spoken_reply": f"I am {persona_name}. I will help you with: {user_prompt}",
            "gesture_description": f"{persona_name} performs a heroic gesture in response to '{user_prompt}'"
        }
        
        try:
            # This is a placeholder for the user's local file
            # In a real scenario, we'd import it
            if os.path.exists('persona_brain.py'):
                import persona_brain
                response_dict = persona_brain.generate_robot_response(user_prompt, persona_name, "")
        except Exception:
            pass
            
        gesture_desc = response_dict.get("gesture_description", "")
        
        # 2. Colab Backend
        video_b64 = ""
        trajectory = []
        try:
            import requests
            url = "https://nonpendent-leonila-unburstable.ngrok-free.dev/generate_motion"
            payload = {"gesture_description": gesture_desc}
            response = requests.post(url, json=payload, timeout=120)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    video_b64 = data.get("video_base64", "")
                    trajectory = data.get("trajectory", [])
        except Exception:
            pass
            
        # 3. MuJoCo Simulation
        sim_video_b64 = ""
        try:
            import mujoco
            import numpy as np
            import imageio
            
            xml_path = "unitree_mujoco/unitree_robots/g1/scene_pinned.xml"
            if os.path.exists(xml_path):
                model = mujoco.MjModel.from_xml_path(xml_path)
                data = mujoco.MjData(model)
                renderer = mujoco.Renderer(model, 480, 640)
                frames = []
                
                if not trajectory:
                    nu = model.nu
                    trajectory = [np.zeros(nu).tolist() for _ in range(60)] # 2 seconds at 30fps
                    
                mujoco.mj_resetData(model, data)
                for row in trajectory:
                    ctrl_len = min(len(row), model.nu)
                    data.ctrl[:ctrl_len] = row[:ctrl_len]
                    mujoco.mj_step(model, data)
                    renderer.update_scene(data)
                    frames.append(renderer.render())
                renderer.close()
                
                output_filename = "sim_output.mp4"
                imageio.mimsave(output_filename, frames, fps=30, macro_block_size=None)
                
                with open(output_filename, "rb") as f:
                    sim_video_b64 = base64.b64encode(f.read()).decode('utf-8')
            else:
                # Mock simulation video if XML is missing
                pass
        except Exception:
            pass
            
        result = {
            "spoken_reply": response_dict.get("spoken_reply", ""),
            "gesture_description": gesture_desc,
            "video_base64": video_b64,
            "sim_video_base64": sim_video_b64
        }
        
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()
