"""Veronica Neural Text-to-Speech Engine.
Uses Microsoft Edge TTS for high-fidelity, expressive neural speech without API keys.
Streams base64 MP3 chunks over the WebSocket session for real-time playback.
"""
from __future__ import annotations

import base64
import logging
from typing import AsyncIterator

import edge_tts

logger = logging.getLogger("veronica.tts")

AVAILABLE_VOICES = [
    {"id": "en-US-AvaNeural", "name": "Ava (Expressive, Modern)", "gender": "Female", "locale": "en-US"},
    {"id": "en-US-JennyNeural", "name": "Jenny (Natural, Warm)", "gender": "Female", "locale": "en-US"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (British, Refined)", "gender": "Female", "locale": "en-GB"},
    {"id": "en-US-GuyNeural", "name": "Guy (Confident, Crisp)", "gender": "Male", "locale": "en-US"},
    {"id": "en-US-ChristopherNeural", "name": "Christopher (Authoritative)", "gender": "Male", "locale": "en-US"},
]

DEFAULT_VOICE = "en-US-AvaNeural"


class EdgeTtsEngine:
    """Streams neural audio chunks for text utterances."""

    def __init__(self, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    def set_voice(self, voice: str) -> None:
        if voice:
            self.voice = voice

    async def stream_audio(self, text: str) -> AsyncIterator[str]:
        """Yield base64-encoded audio chunks (MP3 format)."""
        clean = text.strip()
        if not clean:
            return

        try:
            communicate = edge_tts.Communicate(clean, self.voice, rate=self.rate, pitch=self.pitch)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio" and chunk["data"]:
                    # Return base64 encoded chunk for JSON envelope transport
                    yield base64.b64encode(chunk["data"]).decode("ascii")
        except Exception as exc:
            logger.warning("Edge TTS stream failed, fallback needed: %s", exc)
            # Generator finishes; client-side synthesis will take over if audio is empty
            return
