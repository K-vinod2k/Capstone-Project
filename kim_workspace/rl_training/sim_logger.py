import json
import requests
import time
from datetime import datetime

class SimFailureLogger:
    def __init__(self, vlaw_endpoint="http://127.0.0.1:8080/vlaw_sim_sync"):
        self.vlaw_endpoint = vlaw_endpoint
        self.state_history = []
        
    def log_state(self, joint_angles, base_height, pitch, roll):
        # Keep a rolling buffer of 50 timesteps
        self.state_history.append({
            "joints": joint_angles,
            "base_height": base_height,
            "pitch": pitch,
            "roll": roll
        })
        if len(self.state_history) > 50:
            self.state_history.pop(0)
            
    def check_failure(self):
        if not self.state_history: return False
        
        latest = self.state_history[-1]
        
        # Sim failure condition for G1
        if latest["base_height"] < 0.4 or abs(latest["pitch"]) > 0.5 or abs(latest["roll"]) > 0.5:
            self._trigger_vlaw_handshake()
            return True
        return False
        
    def _trigger_vlaw_handshake(self):
        print("[SimLogger] CRITICAL FAILURE DETECTED in Isaac Lab. Triggering VLAW Handshake.")
        payload = {
            "timestamp": datetime.now().isoformat(),
            "failure_reason": "ZMP Collapse / Base Height threshold exceeded",
            "telemetry_buffer": self.state_history
        }
        
        try:
            # Sync back to Vinod's generator to request a physical recovery animation
            response = requests.post(self.vlaw_endpoint, json=payload, timeout=5)
            if response.status_code == 200:
                print("[SimLogger] Handshake successful. Recovery animation requested.")
            else:
                print(f"[SimLogger] Handshake failed: {response.text}")
        except requests.exceptions.ConnectionError:
            print("[SimLogger] Server not active. Simulating Handshake Success for testing...")
            time.sleep(1)
        except Exception as e:
            print(f"[SimLogger] Handshake network error: {e}")
        
        # Clear buffer after trigger to avoid spam
        self.state_history.clear()
        time.sleep(2) # Cooldown
