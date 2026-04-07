import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Mascot Unitree API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

class VlawSyncRequest(BaseModel):
    timestamp: str
    failure_reason: str
    telemetry_buffer: list

@app.post("/vlaw_sim_sync")
async def vlaw_sim_sync(req: VlawSyncRequest):
    print(f"[VLAW] Received RL Simulation Failure at {req.timestamp}")
    print(f"[VLAW] Reason: {req.failure_reason}")
    
    # Static Fallback proxy routing an array instead of video
    pkl_path = Path(__file__).parent / "output" / "hulk_kinematics.pkl"
    if not pkl_path.exists():
        # Look in current dir as fallback
        pkl_path = Path(__file__).parent / "hulk_kinematics.pkl"
        if not pkl_path.exists():
            raise HTTPException(status_code=404, detail="Recovery static pkl not found.")
        
    print("[VLAW] Topology Node trigger: Routing static Hulk pkl back!")
    return {
        "status": "Success",
        "action": "Recovery trajectory sent",
        "trajectory_proxy": str(pkl_path)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
