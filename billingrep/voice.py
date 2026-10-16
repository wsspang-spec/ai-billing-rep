"""ElevenLabs voice message for a clarification request. Generated only, never delivered."""

import os
import re

from billingrep import config

AUDIO = config.LOCAL / "audio"
MODEL_ID = "eleven_multilingual_v2"
LABEL = "Generated, not delivered"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "message"


def generate_message(text: str, out_name: str) -> dict:
    """Render `text` to local-data/audio/<out_name>.mp3 with ElevenLabs."""
    try:
        if not config.has("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
            return {"error": "ElevenLabs keys not set (ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID)"}
        if not text or not text.strip():
            return {"error": "empty text"}
        from elevenlabs.client import ElevenLabs

        name = _safe(out_name)
        AUDIO.mkdir(parents=True, exist_ok=True)
        path = AUDIO / f"{name}.mp3"
        client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        audio = client.text_to_speech.convert(
            voice_id=os.environ["ELEVENLABS_VOICE_ID"],
            text=text,
            model_id=MODEL_ID,
            output_format="mp3_44100_128",
        )
        with open(path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        if path.stat().st_size == 0:
            return {"error": "ElevenLabs returned no audio"}
        return {"path": str(path), "url": f"/audio/{name}.mp3", "label": LABEL, "chars": len(text)}
    except Exception as e:  # never break the agent loop over a voice message
        return {"error": f"{type(e).__name__}: {str(e)[:300]}"}
