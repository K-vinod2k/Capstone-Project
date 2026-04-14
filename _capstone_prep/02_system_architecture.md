# Topic 2: System Architecture & Pipeline

**What this section covers:** How all the components connect end-to-end, data flow, and how the two machines collaborate.

---

## Section A — Big Picture

**Q1. Walk me through the full pipeline from user input to robot motion — every stage in order.**
> 1. `main.py` receives text or voice input
> 2. `persona_brain.py` (Qwen2.5-72B) selects a hero and returns a gesture description + spoken reply
> 3. `rag_retrieve.py` (FAISS) matches the gesture description to the nearest hero animation PKL
> 4. `mujoco_physics_eval.py` validates the PKL for ZMP/CoM stability
> 5. `deploy_real.py` loads the PKL, eases in over 3 seconds, plays at 500 Hz via DDS to the G1

**Q2. Which parts run on the Mac and which on the Linux machine? Why that split?**
> **Mac (Vinod):** persona engine, video generation, PromptHMR pose extraction, GMR retargeting, MuJoCo physics eval, RAG retrieval, VLAW recovery server. These are compute/API tasks that don't require the robot.
> **Linux (Kim):** Isaac Lab RL training (needs NVIDIA GPU), hardware DDS deployment scripts (needs direct Ethernet to robot). The split follows hardware constraints — GPU training stays on Linux, everything else on Mac.

**Q3. What is the format of data that passes between stages?**
> text → `spoken_reply + gesture_description` (strings from LLM) → `pkl_path` (string from RAG) → `joint_angles` array shape (N, 35) float32 (from PKL file) → `LowCmd_` DDS message (35 motor commands at 500 Hz) → physical robot motion

---

## Section B — Key Design Decisions

**Q4. Why do you use a RAG retrieval system instead of generating a new animation every time?**
> Video generation takes minutes and requires API calls that can fail. RAG retrieval is instant (milliseconds), offline-capable, and returns a pre-validated safe PKL. The video pipeline is used to BUILD the library; RAG is used to SERVE from it at runtime.

**Q5. What is a PKL file? What does it contain, and why is that format used?**
> A Python pickle file containing a dict with key `joint_angles` → numpy array of shape (N, 35) — N frames of 35-motor positions in radians. PKL is used because numpy arrays serialize directly with pickle, it's compact, and the entire Python ecosystem reads it without extra dependencies.

**Q6. Why does the PKL have 35 columns when the robot only has 23 active joints?**
> The Unitree G1 hardware IDL has 35 motor slots regardless of model variant. The LowCmd message always has 35 motor_cmd entries. Indices 23-34 are unused on 23-DOF hardware — they just get zero gains and are ignored by the robot. Keeping 35 columns means the array index matches the IDL index directly with no translation layer.

**Q7. The pipeline has two paths: RAG retrieval and video generation. When does each one activate?**
> RAG retrieval activates at runtime for every user query — it's the live serving path. Video generation activates offline when building or expanding the motion library (running `generate_rag_dataset.py`). The two paths share the same output format (PKL files) so deploy_real.py works identically for both.

---

## Section C — Integration

**Q8. How does main.py tie everything together? What does it actually do?**
> `main.py` is the root CLI. It accepts `--text` or runs in voice mode. It calls `persona_brain.py` to get the hero match and reply, then calls `rag_retrieve.py` to get the PKL path, then calls `deploy_real.py` (or the sim renderer on Mac). It's the single entry point that orchestrates all other modules.

**Q9. If the video generation API is down, what happens? Does the system still work?**
> Yes — the live demo path uses only RAG retrieval against pre-built PKLs. Video generation is only needed when adding new animations to the library. The system degrades gracefully: `persona_brain.py` also falls back to mock mode if HuggingFace token is missing.

**Q10. What is the VLAW loop? Draw the feedback cycle in words: what feeds into what?**
> Isaac Lab detects a fall (root Z < 0.4m) → `sim_logger.py` POSTs crash telemetry to `vinod_workspace/server.py /vlaw_sim_sync` → server returns path to a recovery PKL → `vlaw_orchestrator.py` injects that PKL as imitation learning data into the next training episode → PPO trains on both RL reward AND recovery demonstration → policy learns to avoid falls. Loop repeats on every crash.
