from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="VLAW Sync Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

RECOVERY_PKL = Path(__file__).parent / "hulk_kinematics.pkl"


class VlawSyncRequest(BaseModel):
    timestamp: str
    failure_reason: str
    telemetry_buffer: list


@app.post("/vlaw_sim_sync")
async def vlaw_sim_sync(req: VlawSyncRequest):
    print(f"[VLAW] {req.timestamp}: {req.failure_reason}")
    if not RECOVERY_PKL.exists():
        raise HTTPException(status_code=404, detail="Recovery pkl not found.")
    return {"status": "success", "recovery_pkl": str(RECOVERY_PKL)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
