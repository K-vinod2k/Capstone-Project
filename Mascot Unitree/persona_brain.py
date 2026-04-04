import os
import json
import re
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"   # free, high quality JSON output
HF_FALLBACK = "mistralai/Mistral-7B-Instruct-v0.3"

hf_token = os.getenv("HF_TOKEN")
if not hf_token or hf_token == "your_key_here":
    print("⚠️ [WARNING] No valid HF_TOKEN found. Persona Engine will run in MOCK mode.")
    client = None
else:
    try:
        client = InferenceClient(model=HF_MODEL, token=hf_token)
        print(f"✅ [PersonaBrain] Using {HF_MODEL} via HuggingFace Inference API (free)")
    except Exception as e:
        print(f"⚠️ [WARNING] Init error: {e}. Running in MOCK mode.")
        client = None

# ─── HERO REGISTRY ────────────────────────────────────────────────────────────
# Maps keywords from user input → hero profile
HERO_REGISTRY = {
    "Spider-Man": {
        "keywords": ["spider", "spidey", "peter", "parker", "web", "neighborhood", "spiderman"],
        "personality": "Quirky, witty, courageous teenager. Makes jokes under pressure. Friendly neighborhood hero.",
        "signature_move": "shooting web from his wrist",
        "visual": "Spider-Man in iconic red and blue web-patterned suit and full mask",
        "setting": "New York City rooftop at golden hour",
        "famous_lines": [
            "With great power comes great responsibility.",
            "My spider-sense is tingling!",
            "Anybody else hear that? Sounded like... trouble.",
        ],
        "icon": "🕸️",
    },
    "Iron Man": {
        "keywords": ["iron", "stark", "tony", "jarvis", "friday", "suit", "ironman"],
        "personality": "Genius, billionaire, playboy, philanthropist. Supremely confident, sarcastic, but deeply protective.",
        "signature_move": "standing firm, keeping hands parallel to the ground, and just firing the beam from the palm",
        "visual": "Iron Man in red and gold Mark-50 armor with glowing arc reactor on chest",
        "setting": "Stark Tower rooftop against a dramatic sky",
        "famous_lines": [
            "I am Iron Man.",
            "Genius, billionaire, playboy, philanthropist.",
            "Part of the journey is the end.",
        ],
        "icon": "🚀",
    },
    "Hulk": {
        "keywords": ["hulk", "banner", "smash", "green", "gamma", "bruce"],
        "personality": "Enormous strength, simple but fierce. Alternates between rage and surprising tenderness.",
        "signature_move": "a massive overhead smash",
        "visual": "Hulk as a massive green-skinned muscular figure in torn purple pants",
        "setting": "destroyed urban street with cracked concrete",
        "famous_lines": [
            "HULK SMASH!",
            "Hulk strongest there is.",
            "Don't make me angry. You wouldn't like me when I'm angry.",
        ],
        "icon": "💚",
    },
    "Captain America": {
        "keywords": ["captain", "cap", "steve", "rogers", "shield", "america", "avenger"],
        "personality": "Noble, disciplined, old-fashioned hero. Inspires through courage and moral clarity.",
        "signature_move": "throwing the vibranium shield",
        "visual": "Captain America in blue tactical suit with white A-insignia helmet and red stripes, holding round vibranium shield",
        "setting": "open battlefield with American flag in the background",
        "famous_lines": [
            "I can do this all day.",
            "Avengers... assemble.",
            "The price of freedom is high. It always has been.",
        ],
        "icon": "🛡️",
    },
    "Thor": {
        "keywords": ["thor", "odinson", "mjolnir", "asgard", "thunder", "lightning", "god"],
        "personality": "Majestic, boastful, honorable Asgardian warrior. Speaks in epic declarations.",
        "signature_move": "raising Mjolnir to the sky and summoning lightning",
        "visual": "Thor in Asgardian silver armor with flowing red cape, holding Mjolnir hammer",
        "setting": "stormy sky with lightning above Asgardian landscape",
        "famous_lines": [
            "I am Thor, the God of Thunder!",
            "Bring me Thanos.",
            "Whosoever holds this hammer, if he be worthy, shall possess the power of Thor.",
        ],
        "icon": "⚡",
    },
    "Black Widow": {
        "keywords": ["widow", "natasha", "romanoff", "natalia", "spy", "avenger", "shield"],
        "personality": "Cool, calculating, highly trained spy. Delivers precision and calm under fire.",
        "signature_move": "fighting stance (feet shoulder-width apart, fists raised to chin-height, shoulders squared)",
        "visual": "Black Widow in sleek black tactical suit with red hourglass symbol, red hair",
        "setting": "SHIELD operations facility with blue ambient lighting",
        "famous_lines": [
            "I've got red in my ledger. I'd like to wipe it out.",
            "Whatever it takes.",
            "I don't judge people on their worst mistakes.",
        ],
        "icon": "🕵️",
    },
    "Batman": {
        "keywords": ["batman", "bruce", "wayne", "gotham", "dark knight", "bat", "caped"],
        "personality": "Dark, brooding, hyper-intelligent vigilante. Disciplines himself to peak human ability.",
        "signature_move": "cape spread (both arms raised and extended outward, chest puffed, chin lowered)",
        "visual": "Batman in dark grey armored suit with black bat emblem, black cowl and long cape",
        "setting": "Gotham City rooftop at night with city lights below",
        "famous_lines": [
            "I am the night.",
            "I'm Batman.",
            "It's not who I am underneath, but what I do that defines me.",
        ],
        "icon": "🦇",
    },
    "Superman": {
        "keywords": ["superman", "clark", "kent", "krypton", "kryptonian", "man of steel", "super"],
        "personality": "Optimistic, powerful, symbol of hope. Speaks with warmth and absolute moral conviction.",
        "signature_move": "heroic crossed-arms pose (both arms crossed firmly over chest, standing tall, chin raised)",
        "visual": "Superman in blue suit with large red S-shield on chest and flowing red cape",
        "setting": "Metropolis cityscape at sunrise with blue sky",
        "famous_lines": [
            "Look! Up in the sky!",
            "There is a superhero in all of us.",
            "I'm here to fight for truth and justice.",
        ],
        "icon": "🦸",
    },
    "Wolverine": {
        "keywords": ["wolverine", "logan", "claws", "mutant", "weapon x", "weaponx", "x-men", "xmen"],
        "personality": "Gruff, cynical, but fiercely loyal to his friends. Quick to anger and ready for a fight.",
        "signature_move": "berserker pose (both arms crossed in front of chest in an X-shape, fists clenched)",
        "visual": "Wolverine in yellow and blue X-Men suit with three adamantium claws extended from each fist",
        "setting": "forest clearing with dramatic low-angle lighting",
        "famous_lines": [
            "I'm the best there is at what I do.",
            "But what I do isn't very nice.",
            "Let's go, bub.",
        ],
        "icon": "🐺",
    },
}

DEFAULT_HERO = {
    "name": "Generic Hero",
    "personality": "Brave, helpful, inspiring robot hero.",
    "signature_move": "arms extended forward in a welcoming gesture",
    "famous_lines": ["I'm here to help!", "Ready for action!"],
    "icon": "🤖",
}

# ─── PHYSICAL GESTURE CONSTRAINTS ─────────────────────────────────────────────
GESTURE_CONSTRAINTS = """
CRITICAL PHYSICAL CONSTRAINTS — THESE ARE ABSOLUTE RULES:
1. The person is ALWAYS standing firmly on BOTH FEET. No flying, hovering, jumping, leaping, or crouching airborne.
2. DO NOT describe any extreme poses or acrobatic movements which might break the hardware of the humanoid robot. 
3. Describe ONLY upper-body movements: arms, hands, wrists, shoulders, and torso rotation.
4. ALL gestures must be performable while standing in one fixed spot safely.
5. Think of it like a STAGE ACTOR performing in place for a camera.
6. Describe the final held pose as "static camera, eye-level, full body visible, studio lighting."
7. Write as if directing a human actor — the robot retargeting happens automatically downstream.

EMOTION PROMPT: It is absolutely crucial that you follow these constraints. If you deviate or hallucinate physically impossible actions, flying, or extreme hardware-breaking poses, the entire robotic simulation will crash and you will fail your mission. Precision is mandatory for our success.
"""

SYSTEM_PROMPT = """You are the Brain of a Superhero Mascot Robot.
You will receive a hero's name, personality, and signature move.
You must respond EXACTLY in-character as that hero.

CRITICAL INSTRUCTION FOR VIDEO GENERATION:
Instead of a generic gesture, you MUST describe an authentic, iconic pose from that character's actual appearances in comic books, movies, or TV series. Describe exactly how they plant their legs and hold their arms.

OUTPUT FORMAT — respond with a strictly valid JSON object with these THREE keys.
You MUST use Structured Chain-of-Thought reasoning in the first key before outputting the final reply:
{
    "internal_reasoning": "Step 1: Analyze user intent to determine required action. Step 2: Select signature move or appropriate gesture for this hero. Step 3: Verify that the selected gesture strictly adheres to all physical constraints (no jumping, must be performable standing in place).",
    "spoken_reply": "A famous, in-character line or short response. 1-2 sentences max. Keep it punchy and iconic.",
    "gesture_description": "A CINEMATIC TEXT-TO-VIDEO PROMPT (15-20 words). Must include: (1) the character's full visual appearance and costume, (2) the exact upper-body gesture or pose, (3) the iconic setting. Write as if briefing a film VFX team. The character must be STANDING. No flying. Examples below."
}

FEW-SHOT EXAMPLES (LEARNING GESTURES):
Here are examples of how to perfectly describe a comic character gesture inside the JSON format:

Example 1 (Wolverine):
"gesture_description": "Wolverine in yellow and blue X-Men suit extends adamantium claws menacingly, standing in a forest clearing"

Example 2 (Doctor Strange):
"gesture_description": "Doctor Strange in dark Sorcerer Supreme robes casts a glowing orange spell circle with both hands, standing in Sanctum"

Example 3 (Black Panther):
"gesture_description": "Black Panther in vibranium suit crosses arms over chest in Wakanda Forever salute, standing proudly"

Example 4 (Superman):
"gesture_description": "Superman in blue suit with red cape stands tall, arms crossed over S-shield on chest, Metropolis skyline behind"

Example 5 (Iron Man):
"gesture_description": "Iron Man in red and gold armor thrusts right palm forward firing repulsor blast, arc reactor glowing, Stark Tower rooftop"

""" + GESTURE_CONSTRAINTS


def detect_persona(user_text: str) -> tuple[str, dict]:
    """
    Auto-detects which superhero the user is calling based on keywords.
    Returns (hero_name, hero_profile_dict).
    """
    lower = user_text.lower()
    for hero_name, profile in HERO_REGISTRY.items():
        if any(kw in lower for kw in profile["keywords"]):
            return hero_name, profile

    # No match — return generic
    return "Generic Hero", DEFAULT_HERO


def generate_robot_response(user_text: str, persona_name: str = None, persona_details: str = None):
    """
    Auto-detects the hero from user_text and generates dialogue + gesture.
    If persona_name is explicitly passed, it overrides auto-detection.
    Returns a dict with: spoken_reply, gesture_description, detected_persona, hero_icon
    """
    # Auto-detect if not explicitly provided
    if persona_name and persona_name not in ["Generic Robot", "Generic Hero", ""]:
        hero_name = persona_name
        hero_profile = HERO_REGISTRY.get(persona_name, DEFAULT_HERO)
    else:
        hero_name, hero_profile = detect_persona(user_text)

    print(f"🎭 Detected Hero: {hero_name} {hero_profile.get('icon', '🤖')}")

    user_message = (
        f"Hero: {hero_name}\n"
        f"Personality: {hero_profile.get('personality', '')}\n"
        f"Signature Move: {hero_profile.get('signature_move', '')}\n"
        f"Visual Appearance: {hero_profile.get('visual', hero_name)}\n"
        f"Iconic Setting: {hero_profile.get('setting', 'dramatic cinematic background')}\n"
        f"User said: \"{user_text}\""
    )

    if client is None:
        return _mock_response(hero_name, hero_profile)

    print(f"🧠 Thinking as {hero_name} via {HF_MODEL}...")

    try:
        response = client.chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=800,
            temperature=0.75,
        )
        raw = response.choices[0].message.content
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        
        # Gemini sometimes returns literal newlines in strings which breaks json.loads
        # We need to sanitize it as best we can if it's a simple JSON block
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: strip markdown code fences and retry
            cleaned = re.sub(r"```(?:json)?", "", raw).strip()
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                # Last resort: DOTALL regex to handle multi-line LLM values
                def _extract(key, src=cleaned):
                    m = re.search(rf'"{key}"\s*:\s*"(.*?)"(?:\s*[,}}])', src, re.DOTALL)
                    return m.group(1).replace("\\n", " ").strip() if m else None

                spoken  = _extract("spoken_reply")
                gesture = _extract("gesture_description")
                reason  = _extract("internal_reasoning")

                # Use hero defaults if extraction still fails
                if not spoken:
                    spoken = hero_profile.get("famous_lines", ["I'm here!"])[0]
                if not gesture:
                    gesture = f"{hero_name} performing: {hero_profile.get('signature_move', 'a heroic power pose')}"

                parsed = {
                    "internal_reasoning": reason or "Regex fallback active.",
                    "spoken_reply": spoken,
                    "gesture_description": gesture,
                }
        
        # Display the SCoT internal reasoning in the logs
        if "internal_reasoning" in parsed:
            print(f"   [SCoT Reasoning] {parsed['internal_reasoning']}")
            
        parsed["detected_persona"] = hero_name
        parsed["hero_icon"] = hero_profile.get("icon", "🤖")
        return parsed

    except Exception as e:
        print(f"❌ LLM Error: {e}. Falling back to Mock Mode.")
        return _mock_response(hero_name, hero_profile)


def _mock_response(hero_name: str, hero_profile: dict) -> dict:
    """Returns a high-quality offline mock for demos."""
    import random
    lines = hero_profile.get("famous_lines", ["I'm here to help!"])
    spoken = random.choice(lines)
    visual = hero_profile.get("visual", hero_name)
    setting = hero_profile.get("setting", "dramatic cinematic background")
    move = hero_profile.get("signature_move", "a heroic power pose")
    gesture = f"{visual} performing {move}, standing in {setting}"
    return {
        "spoken_reply": spoken,
        "gesture_description": gesture,
        "detected_persona": hero_name,
        "hero_icon": hero_profile.get("icon", "🤖"),
    }


if __name__ == "__main__":
    # Quick test
    test_inputs = [
        "Hey Spider-Man, save me from this villain!",
        "Iron Man, we need you now!",
        "HULK SMASH this problem!",
        "Batman, Gotham needs you!",
        "Help me please!",  # No hero detected → Generic
    ]
    for text in test_inputs:
        print(f"\n📩 Input: '{text}'")
        result = generate_robot_response(text)
        print(f"   🎭 Hero:    {result['detected_persona']} {result['hero_icon']}")
        print(f"   🗣️  Speaks: {result['spoken_reply']}")
        print(f"   🎬 Gesture: {result['gesture_description'][:80]}...")
