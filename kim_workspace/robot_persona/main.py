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

        if distances[0][0] > 0.5:
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
        self.search_model = SemanticSearch(movement_directory=movement_directory)
        self.pipe = pipeline("text-generation",
                             model="google/gemma-3-1b-it", 
                             device="cuda",
                             dtype=torch.bfloat16)
        
        self.messages = [[{"role": "system",
                           "content": [{"type": "text", 
                                        "text": f"You are role-playing as {self.persona}."}]}]]
        
    def forward(self, input_text):
        self.messages[0].append({"role": "user",
                               "content": [{"type": "text",
                                            "text": prompt_format(input_text, self.persona)},]})
        
        llm_output = self.pipe(self.messages, 
                               max_new_tokens=50, 
                               generation_config=None)[0][0]["generated_text"][-1]
        
        self.messages[0].append(llm_output)

        return {
            "text": llm_output['content'],
            "gesture": self.search_model.query(input_text)
        }

if __name__ == "__main__":
    
    # Inputs
    persona = "a Superhero"
    movement_directory = './movements'

    # Models
    HF_TOKEN = os.getenv('HF_TOKEN')
    model = RobotPersona(persona, movement_directory)

    while True:
        input_text = input("[USER INPUT] ")
        result = model.forward(input_text)

        print(result["text"])
        print(result["gesture"])
        print()