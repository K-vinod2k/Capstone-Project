# Phase 2: Static Video Extraction & Cost Reduction

**Goal:** Completely eliminate the reliance on paid/rate-limited Cosmos/fal.ai video generation APIs by extracting the Hulk segment from the local `videoplayback.mp4` and hardwiring it into the server architecture.

## To-Do List

- [ ] **2.1. Timestamp Analysis:** Manually or programmatically identify the exact `start_time` and `end_time` (mm:ss) of the Hulk smashing Loki sequence inside the root `videoplayback.mp4`.
- [ ] **2.2. FFmpeg Extraction:** Write and execute an `extract_hulk.py` script running FFmpeg to crop the video without losing resolution or framerate.
- [ ] **2.3. Save to Local Cache:** Output the extracted video as `vinod_workspace/Phase_2/hulk_smash_static.mp4`.
- [ ] **2.4. Server API Overhaul:** Modify `server.py` to intercept any requests for Hulk (or generic aggressive actions). Instead of routing to `hf_video_client.py` and waiting 2 minutes for API generation, instantly load `hulk_smash_static.mp4`.
- [ ] **2.5. Safe Fallback Logic:** If constraints allow, use the free Hugging Face API purely for LLM-based text parsing (Persona detection), but keep video fetching strictly local.
- [ ] **2.6. Delete Original Video (Optional):** Once the Hulk clip is safely extracted and verified, consider deleting the massive 700MB `videoplayback.mp4` from the repo root to drastically speed up Git syncing.
- [ ] **2.7. Phase 2 Checkpoint Log:** Commit the extraction and proxy rewrite to Git.
  - `git add . && git commit -m "feat(phase2): implement zero-cost static hulk video proxy"`
