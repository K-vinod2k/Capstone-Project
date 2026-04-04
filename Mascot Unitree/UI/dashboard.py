import streamlit as st
import requests
import base64
import json
import os
import numpy as np
import imageio
import mujoco

# Try to import the local persona engine, fallback to a mock if not found
try:
    from persona_brain import generate_robot_response
except ImportError:
    def generate_robot_response(user_text, persona_name, persona_details=""):
        # Mock implementation for testing
        return {
            "spoken_reply": f"I am {persona_name}. I will help you with: {user_text}",
            "gesture_description": f"{persona_name} performs a heroic gesture in response to '{user_text}'"
        }

# --- Helper Functions ---

def call_colab_backend(gesture_description):
    """
    Securely posts the gesture_description to the Ngrok URL.
    Parses the video_base64 and saves it locally as generated_ai.mp4.
    Extracts and returns the trajectory matrix.
    """
    url = "https://nonpendent-leonila-unburstable.ngrok-free.dev/generate_motion"
    payload = {"gesture_description": gesture_description}
    
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "success":
            # Save the base64 video
            video_b64 = data.get("video_base64", "")
            if video_b64:
                video_bytes = base64.b64decode(video_b64)
                with open("generated_ai.mp4", "wb") as f:
                    f.write(video_bytes)
            
            trajectory = data.get("trajectory", [])
            return trajectory
        else:
            st.error(f"Backend returned an error: {data.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        st.error(f"Failed to connect to Colab backend: {e}")
        return None

def render_mujoco_trajectory(trajectory, output_filename="sim_output.mp4"):
    """
    Runs MuJoCo headlessly using mujoco.Renderer, renders the physics loop to an MP4 video.
    """
    xml_path = "unitree_mujoco/unitree_robots/g1/scene_pinned.xml"
    
    try:
        model = mujoco.MjModel.from_xml_path(xml_path)
        data = mujoco.MjData(model)
    except Exception as e:
        st.warning(f"Could not load MuJoCo model from {xml_path}. Using a mock rendering process. Error: {e}")
        # Mock rendering if model is not found
        frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(30)]
        imageio.mimsave(output_filename, frames, fps=30)
        return output_filename

    renderer = mujoco.Renderer(model, 480, 640)
    frames = []
    
    # Fallback trajectory if empty
    if not trajectory or len(trajectory) == 0:
        st.info("Empty trajectory received. Using fallback 100-frame Hero pose.")
        # Assuming ctrl has some dimension, e.g., model.nu
        nu = model.nu
        trajectory = [np.zeros(nu).tolist() for _ in range(100)]
        
    mujoco.mj_resetData(model, data)

    for row in trajectory:
        # Ensure the row matches the number of actuators
        ctrl_len = min(len(row), model.nu)
        data.ctrl[:ctrl_len] = row[:ctrl_len]
        
        mujoco.mj_step(model, data)
        renderer.update_scene(data)
        pixels = renderer.render()
        frames.append(pixels)
        
    renderer.close()
    
    # Save to mp4
    imageio.mimsave(output_filename, frames, fps=30, macro_block_size=None)
    return output_filename

# --- Streamlit UI ---

st.set_page_config(page_title="Voice to Robot Movement Pipeline", layout="wide")

st.title("🤖 Voice to Robot Movement Pipeline")
st.markdown("Generative AI Robotics Dashboard combining Text Prompts, LLM Output, GenAI Video, and 3D Simulated Robot rendering.")

# Sidebar
st.sidebar.header("Configuration")
persona_name = st.sidebar.selectbox(
    "Select Persona",
    ['Iron Man', 'Spider-Man', 'Generic Robot']
)
user_prompt = st.sidebar.text_area("User Prompt", "Help, I'm falling!")
generate_btn = st.sidebar.button("Generate Robot Motion", type="primary", use_container_width=True)

if generate_btn:
    if not user_prompt.strip():
        st.sidebar.error("Please enter a user prompt.")
    else:
        with st.spinner("🧠 Generating Persona Response..."):
            # 1. Generate Persona Response
            persona_details = f"A heroic {persona_name} persona."
            response_dict = generate_robot_response(user_prompt, persona_name, persona_details)
            
            spoken_reply = response_dict.get("spoken_reply", "")
            gesture_desc = response_dict.get("gesture_description", "")
            
        # Display Thought Process
        st.subheader("Persona Engine Thought Process")
        col_reply, col_action = st.columns(2)
        with col_reply:
            st.info(f"**Robot Replies:**\n\n{spoken_reply}")
        with col_action:
            st.success(f"**Action Generated:**\n\n{gesture_desc}")
            
        st.divider()
        
        # 2. Call Colab Backend & 3. Render MuJoCo
        col_video, col_sim = st.columns(2)
        
        with col_video:
            st.subheader("AI Video Preview")
            with st.spinner("🎥 Generating AI Video from Colab..."):
                trajectory = call_colab_backend(gesture_desc)
                
            if os.path.exists("generated_ai.mp4"):
                st.video("generated_ai.mp4")
            else:
                st.warning("AI Video not available or failed to generate.")
                
        with col_sim:
            st.subheader("Physical Robot Simulation")
            if trajectory is not None:
                with st.spinner("⚙️ Rendering MuJoCo Simulation..."):
                    sim_output_path = render_mujoco_trajectory(trajectory, "sim_output.mp4")
                    
                if os.path.exists(sim_output_path):
                    st.video(sim_output_path)
                else:
                    st.error("Failed to render MuJoCo simulation.")
            else:
                st.error("Cannot render simulation: No trajectory received.")
