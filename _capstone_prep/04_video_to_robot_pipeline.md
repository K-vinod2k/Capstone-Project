# Topic 4: Video-to-Robot Motion Pipeline

**What this section covers:** How a text prompt becomes a robot-ready joint angle trajectory through video generation and pose estimation.

---

## Section A — Video Generation

**Q1. What two video generation APIs does your pipeline support? What is the fallback order?**
> Primary: Google Veo (`GOOGLE_API_KEY`). Fallback: OpenAI Sora (`OPENAI_API_KEY`). The pipeline tries Veo first; if unavailable or the API call fails, it falls back to Sora. Both produce short MP4 clips of a person performing the requested action.

**Q2. Given the prompt "Hulk smashes the ground," what does the video generation step output?**
> A short MP4 video (typically 3-5 seconds) showing a person or humanoid figure performing a two-handed overhead smash motion. This video serves as the motion reference for PromptHMR.

**Q3. Why generate a video at all? Why not go directly from text to joint angles?**
> Text alone lacks physical grounding — "smash" doesn't specify joint trajectories, timing, or body dynamics. A video provides: (a) temporal motion sequence frame by frame, (b) 3D body pose cues, (c) physical plausibility (a real person doing the motion naturally obeys biomechanical constraints). This is much richer than any text-to-joint-angles model could infer from text alone.

---

## Section B — Human Pose Estimation (PromptHMR)

**Q4. What does PromptHMR do? What are its inputs and outputs?**
> Input: video frames (MP4). Output: per-frame SMPL-X body parameters — a sequence of pose vectors describing the full human body configuration at each frame. It uses a transformer-based model guided by text prompts to improve pose accuracy.

**Q5. What is SMPL-X? Why use a parametric body model rather than raw keypoints?**
> SMPL-X (Skinned Multi-Person Linear model eXpressive) is a parametric 3D human body model with 144 pose parameters covering body, hands, and face. Better than raw keypoints because: (a) it's a consistent parameterization across all body types, (b) pose parameters can be directly retargeted to a robot skeleton, (c) it enforces biomechanical constraints (e.g., no impossible elbow bends).

**Q6. PromptHMR runs in a separate conda environment (phmr). Why the isolation?**
> PromptHMR requires Python 3.11 and specific versions of PyTorch/CUDA that conflict with the main pipeline's dependencies. Conda environment isolation prevents version conflicts without Docker overhead.

**Q7. What information is lost when you go from video to SMPL-X pose? What is preserved?**
> **Lost:** appearance (clothing, skin), environment context, precise 3D scale/depth (monocular ambiguity), fine finger motion.
> **Preserved:** body joint angles, temporal motion sequence, relative limb positions, overall body configuration per frame.

---

## Section C — Retargeting (GMR)

**Q8. What does GMR do? Why can't you use the SMPL-X angles directly on the robot?**
> GMR (Generalized Motion Retargeting) converts SMPL-X human pose parameters to G1 robot joint angles. You can't use SMPL-X directly because: the human model has 144 parameters for a ~1.7m body with hands and face; the G1 has 23 active DOF with different link lengths, no hands, and no facial expression capability. The angle of a human shoulder doesn't map 1:1 to the robot's shoulder — GMR solves the IK/mapping problem.

**Q9. What is the difference between a human body and the G1's joint structure that makes retargeting necessary?**
> Human body: ~72 body joints + hands + face, variable proportions, continuous joint limits. G1 23-DOF: 12 leg joints, 1 waist, 10 arm joints (5 per arm, no wrists). The G1 is shorter-limbed, has no fingers, and its joints have hard mechanical limits (e.g., elbow can only bend one way). Retargeting rescales and remaps the motion to physically feasible G1 configurations.

**Q10. GMR also runs in a separate conda environment (gmr). What Python version does it require and why?**
> Python 3.10. GMR depends on specific versions of PyTorch geometric libraries and retargeting tools that aren't compatible with Python 3.11 (used by PromptHMR) or 3.12+. The `run_in_conda()` helper in `video2robot/` handles switching environments automatically via subprocess.

**Q11. What is the output of GMR — what format, what shape, how many joints?**
> A PKL file with key `joint_angles` → numpy array shape `(N, 35)` float32. N = number of frames at 30 FPS. 35 columns matching the G1 hardware IDL — 23 active joints filled in, indices 23-34 left as zeros.

---

## Section D — The Full Chain

**Q12. Trace a single frame through the entire pipeline: video pixel → SMPL-X parameter → G1 joint angle.**
> 1. Video frame pixel array → PromptHMR → SMPL-X pose vector (e.g., left shoulder angle = 1.2 rad in body frame)
> 2. SMPL-X pose vector → GMR solver → G1 joint angle (e.g., L_shoulder_pitch IDL index 13 = -0.9 rad, accounting for different link lengths)
> 3. G1 joint angle → PKL row → deploy_real.py interpolation → `motor_cmd[13].q = -0.9` in LowCmd

**Q13. What could cause motion artifacts or jerky output at each stage?**
> - Video gen: inconsistent lighting or blurry frames → bad pose estimates
> - PromptHMR: monocular depth ambiguity → flipped limbs
> - GMR: out-of-range retargeted angles → clamp artifacts
> - clamp_pkls.py: velocity clamping upsamples frames → smoother but slower motion

**Q14. How long does the full video-to-PKL pipeline take end-to-end?**
> Approximately: video generation (30-120s API call) + PromptHMR inference (60-120s on GPU) + GMR retargeting (30-60s) = roughly 2-5 minutes total. This is why RAG serves pre-built PKLs at runtime rather than regenerating on every query.
