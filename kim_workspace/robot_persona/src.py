from transformers import pipeline
import torch
import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os

class SemanticSearch:
    def __init__(self, movement_directory='./movements'):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.sentences = os.listdir(movement_directory)
        self.embeddings = self.model.encode(self.sentences)
        d = self.embeddings.shape[1]
        self.index = faiss.IndexFlatL2(d)
        self.index.add(self.embeddings.astype('float32'))

    def query(self, query, k=1):
        query_vector = self.model.encode([query])

        distances, indices = self.index.search(query_vector.astype('float32'), k)

        return self.sentences[indices[0][0]]

def prompt_format(input_text, persona):
    return f"""
    The user is saying the following:
    {input_text}

    Given this user input, return a reply that is in line with the designated persona ({persona}). Keep the reply short, below 20 words."""

class RobotPersona:
    """
    Input Arguments:
    - persona: str (LLM Persona)
    - movement_directory: str (Directory containing gesture .pkl files)
    
    Output: dict()
    * Keys:
    - text: str (Robot Output String)
    - gesture: str (Robot Gesture Pickle File)
    
    """
    def __init__(self, persona, movement_directory):
        self.persona = persona
        self.movement_directory = movement_directory
        self.search_model = SemanticSearch(movement_directory=movement_directory)

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        device = "cuda" if torch.cuda.is_available() else device

        self.pipe = pipeline("text-generation",
                             model="Qwen/Qwen2.5-0.5B-Instruct",
                             device=device,
                             dtype=torch.bfloat16)
        
        self.messages = [[{"role": "system",
                           "content": f"You are role-playing as {self.persona}."}]]

    def forward(self, input_text):
        gesture_file = self.search_model.query(input_text)
        replies = {
            "wave": "Hey there! *waves*",
            "flex": "Nobody is stronger than me!",
            "punch": "Take that!",
            "hulk_smash": "HULK SMASH!",
            "iron_man_repulsor": "Repulsors online. Back off.",
            "spider_man_web_shoot": "Your friendly neighborhood Spider-Man!",
            "spider_man_landing": "Just dropped in.",
            "captain_america_shield": "I can do this all day.",
            "thor_lightning": "I am the God of Thunder!",
            "wolverine_claws": "I'm the best there is at what I do.",
        }
        name = gesture_file.replace("_kinematics.pkl", "") if gesture_file else "wave"
        text = replies.get(name, "Hero mode activated!")
        print(f"[ROBOT] {text}")
        return {
            "text": text,
            "gesture": os.path.join(self.movement_directory, gesture_file) if gesture_file else None
        }

if __name__ == "__main__":
    
    # Inputs
    persona = "a Superhero"
    movement_directory = './movements'

    # Models
    load_dotenv()
    HF_TOKEN = os.getenv('HF_TOKEN')
    model = RobotPersona(persona, movement_directory)

    while True:
        input_text = input("[USER INPUT] ")
        result = model.forward(input_text)

        print(result["text"])
        print(result["gesture"])
        print()
