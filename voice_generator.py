"""
voice_generator.py
Converts a script string to an MP3 file using the ElevenLabs API.
"""

import os
import requests
import config

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def generate_voiceover(script: str, output_path: str = "voiceover.mp3") -> str:
    """
    Sends `script` to ElevenLabs and saves the result as an MP3.
    Returns the absolute path to the saved file.
    """
    url = ELEVENLABS_API_URL.format(voice_id=config.ELEVENLABS_VOICE_ID)

    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": script,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    response = requests.post(url, json=payload, headers=headers, timeout=120)
    response.raise_for_status()

    abs_path = os.path.abspath(output_path)
    with open(abs_path, "wb") as f:
        f.write(response.content)

    print(f"[voice] Saved voiceover → {abs_path} ({len(response.content) // 1024} KB)")
    return abs_path


if __name__ == "__main__":
    test_script = "Welcome to Smart Money Daily. Today we are talking about the five best ways to save money in 2026."
    generate_voiceover(test_script, "test_voice.mp3")
