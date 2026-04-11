# Robot Persona
Converts text input into persona output & locates relevant movement file.

## Installation
The project can be run on a virtual environment:

```
conda create -n robot_persona python=3.12
conda activate robot_persona
pip install -r requirements.txt
```

After completing the virtual environment installation, open the `.env` file and insert your Hugging Face API token.

## Usage
The `main.py` file contains the `RobotPersona` class, which is responsible for converting user prompts into LLM responses and corresponding gestures. For Demo Usage in the virtual environment:

```
python src.py
```
