import asyncio
import pickle
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from persona_brain import generate_robot_response
from pipeline import (
    PHYSICAL_BOOSTER, generate_video, get_base64_video,
    render_mujoco_trajectory, render_unitree_frame,
    verify_stability, video_ready, verify_sim_to_real
)

app = FastAPI(title="Mascot Unitree API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


class PipelineRequest(BaseModel):
    user_prompt: str
    selected_persona: str = ""


class PipelineResponse(BaseModel):
    spoken_reply: str
    gesture_description: str
    detected_persona: str
    hero_icon: str
    reference_video_b64: str
    simulation_video_b64: str
    sim_to_real_safe: bool
    sim_to_real_reasoning: str


@app.post("/api/run_pipeline", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest):
    # 1. Persona engine
    response         = generate_robot_response(req.user_prompt, req.selected_persona or None)
    spoken_reply     = response.get("spoken_reply", "I lack a voice.")
    gesture_desc     = response.get("gesture_description", "Standing still.")
    detected_persona = response.get("detected_persona", "Generic Hero")
    hero_icon        = response.get("hero_icon", "🤖")

    # 2. Physics gate (Cosmos-Reason2 + Unitree G1 render)
    robot_frame = render_unitree_frame()
    physics = verify_stability(gesture_desc, robot_frame_b64=robot_frame)
    if not physics["is_stable"]:
        raise HTTPException(status_code=400, detail=physics["reasoning"])

    # 3. Video generation
    if not video_ready:
        raise HTTPException(status_code=500, detail="No video backend — set FAL_KEY or COLAB_URL.")
    result = generate_video(gesture_desc + PHYSICAL_BOOSTER, duration=6, resolution="720p")
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    ref_video_b64 = result["video_base64"]

    # 4. Motion — load pre-computed G1 demo motion
    DEMO_PKL = Path(__file__).parent / "output" / "2026-03-12_07-07-09.pkl"
    with open(DEMO_PKL, "rb") as f:
        trajectory = pickle.load(f)

    # 5. Render
    render_mujoco_trajectory(trajectory, "sim_output.mp4")

    # 6. Sim-To-Real World Model Validation
    sim_to_real_result = verify_sim_to_real("sim_output.mp4")

    return {
        "spoken_reply": spoken_reply,
        "gesture_description": gesture_desc,
        "detected_persona": detected_persona,
        "hero_icon": hero_icon,
        "reference_video_b64": f"data:video/mp4;base64,{ref_video_b64}",
        "simulation_video_b64": f"data:video/mp4;base64,{get_base64_video('sim_output.mp4')}",
        "sim_to_real_safe": sim_to_real_result.get("is_safe_for_real_hardware", True),
        "sim_to_real_reasoning": sim_to_real_result.get("reasoning", "Verification complete."),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
