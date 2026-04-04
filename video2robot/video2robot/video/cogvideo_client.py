"""
CogVideo Video Generation Client (Hugging Face)

Usage:
    from video2robot.video import CogVideoClient

    client = CogVideoClient(model_id="THUDM/CogVideoX-5b")
    video_path = client.generate("A person dancing", output_path="output.mp4")
"""

from __future__ import annotations

import gc
import torch
import numpy as np
import shutil
from pathlib import Path
from typing import Optional, Union, List

from diffusers import CogVideoXPipeline
from diffusers.utils import export_to_video

from video2robot.utils import emit_progress


class CogVideoClient:
    """CogVideo Video Generation Client"""

    def __init__(
        self,
        model_id: str = "THUDM/CogVideoX-5b",
        dtype: str = "float16",
        enable_sequential_cpu_offload: bool = True,
        enable_slicing: bool = True,
        enable_tiling: bool = True,
    ):
        """
        Initialize CogVideo Client

        Args:
            model_id: HuggingFace model ID (e.g. THUDM/CogVideoX-5b)
            dtype: Precision ("float16" recommended for Mac)
            enable_sequential_cpu_offload: Save memory by offloading models to CPU
            enable_slicing: Save memory by slicing attention computation
        """
        self.model_id = model_id
        self.dtype_str = dtype
        self.dtype = getattr(torch, dtype)
        self.enable_sequential_cpu_offload = enable_sequential_cpu_offload
        self.enable_slicing = enable_slicing
        self.enable_tiling = enable_tiling
        self.pipeline = None
        
        # Detect device
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        
        print(f"[CogVideo] Initialized with device: {self.device}, dtype: {dtype}")

    def _load_pipeline(self):
        """Lazy load pipeline"""
        if self.pipeline is not None:
            return

        print(f"[CogVideo] Loading pipeline: {self.model_id}...")
        emit_progress("init", 0.05, "Loading Model")
        
        try:
            pipe = CogVideoXPipeline.from_pretrained(
                self.model_id,
                torch_dtype=self.dtype
            )

            # Optimizations
            if self.enable_sequential_cpu_offload and self.device == "cuda":
                # CUDA specific optimizations
                pipe.enable_model_cpu_offload() # prefer model offload over sequential for CogVideo? Usually sequential helps more with VRAM
                pipe.enable_sequential_cpu_offload()
            else:
                # MPS or CPU
                pipe.to(self.device)

            if self.enable_slicing:
                pipe.vae.enable_slicing()
            
            if self.enable_tiling:
                pipe.vae.enable_tiling()

            self.pipeline = pipe
            print(f"[CogVideo] Pipeline loaded.")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Failed to load CogVideo pipeline: {e}")

    def generate(
        self,
        prompt: str,
        output_path: str,
        num_inference_steps: int = 50,
        guidance_scale: float = 6.0,
        num_frames: int = 49,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        **kwargs
    ) -> Path:
        """
        Generate video using CogVideo

        Args:
            prompt: Text description
            output_path: Output video path
            num_inference_steps: Denoising steps
            guidance_scale: Classifier-free guidance scale
            num_frames: Number of frames to generate
            seed: Random seed
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self._load_pipeline()
        
        # Setup generator
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed) # CPU generator is safer across devices
        
        print(f"[CogVideo] Generating video...")
        print(f"[CogVideo] Prompt: {prompt[:100]}...")
        
        # Callback for progress
        def callback_dynamic(pipeline, step_index, timestep, callback_kwargs):
            # Report progress
            progress = step_index / num_inference_steps
            # Map 0-1 to 0.1-0.9
            mapped_progress = 0.1 + (progress * 0.8)
            emit_progress("generating", mapped_progress, f"Generating step {step_index}/{num_inference_steps}")
            return callback_kwargs

        try:
            # Generate
            output = self.pipeline(
                prompt=prompt,
                num_frames=num_frames,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                generator=generator,
                export_to_video=True,
                negative_prompt=negative_prompt,
                callback_on_step_end=callback_dynamic,
            ).frames[0]
            
            print(f"[CogVideo] Saving video to {output_path}...")
            export_to_video(output, str(output_path), fps=8)
            
            print(f"[CogVideo] Done.")
            emit_progress("done", 1.0, "Done")
            
        except Exception as e:
            raise RuntimeError(f"Generation failed: {e}")
            
        return output_path
