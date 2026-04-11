import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
import queue
import torch

class STT:
    def __init__(self):
        # --- Configuration ---
        MODEL_SIZE = "base"

        device = "cuda" if torch.cuda.is_available() else "cpu"

        COMPUTE_TYPE = "float16" if device == "cuda" else "int8"
        self.SAMPLERATE = 16000
        self.SILENCE_DURATION = 1.5  # Seconds of silence before "ending" a sentence
        self.SILENCE_THRESHOLD = 0.01 # Volume threshold (adjust based on your mic)

        # --- Initialize ---
        self.model = WhisperModel(MODEL_SIZE, device=device, compute_type=COMPUTE_TYPE)
        self.audio_queue = queue.Queue()
        self.audio_buffer = []

    def audio_callback(self, indata, frames, time, status):
        if status:
            print(status)
        # Put raw audio into a queue to process outside the interrupt
        self.audio_queue.put(indata.copy().flatten())

    def process_audio(self, persona_func=None, action_func=None):
        silence_counter = 0
        
        print("Listening... (Speak now)")
        
        while True:
            # Get audio chunk from queue
            chunk = self.audio_queue.get()
            self.audio_buffer.extend(chunk)
            
            # Check the volume of the current chunk (Root Mean Square)
            rms = np.sqrt(np.mean(chunk**2))
            
            if rms < self.SILENCE_THRESHOLD:
                silence_counter += len(chunk) / self.SAMPLERATE
            else:
                silence_counter = 0 # Reset if noise is detected

            # If silence exceeds our threshold AND we actually have audio to process
            if silence_counter >= self.SILENCE_DURATION and len(self.audio_buffer) > self.SAMPLERATE:
                # Convert buffer to numpy array for Whisper
                full_audio = np.array(self.audio_buffer).astype(np.float32)
                
                # Transcribe
                segments, _ = self.model.transcribe(full_audio, beam_size=1, language="en")
                text = "".join([s.text for s in segments]).strip()
                
                if text:
                    print(f"[USER] {text}")
                    if persona_func:
                        robot_reply = persona_func(text)
                        print(f"[ROBOT] {robot_reply['text']}")
                        print(f"[ACTION] {robot_reply['gesture']}")

                        if action_func and robot_reply['gesture']:
                            action_func(robot_reply['gesture']) # Pickle -> Robot Gesture
                
                # Clear buffer and reset counter
                self.audio_buffer = []
                silence_counter = 0


if __name__ == "__main__":
    model = STT()
    
    # Start the stream in a background thread
    stream = sd.InputStream(samplerate=model.SAMPLERATE, channels=1, callback=model.audio_callback)
    with stream:
        model.process_audio()
