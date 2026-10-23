"""Model adapter seams. Real STT/TTS/LLM backends implement these; the core never imports them directly.

Only the LLM seam exists in this foundation. STT and TTS seams are added in roadmap phases 2 and 3,
when there is a concrete backend to validate the interface against (avoids speculative abstraction).
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol


class LlmAdapter(Protocol):
    def respond(self, text: str) -> AsyncIterator[str]:
        """Yield response text chunks for a user utterance."""
        ...


class EchoLlm:
    """Deterministic offline stand-in. Lets the pipeline be tested with no model, network or key."""

    async def respond(self, text: str) -> AsyncIterator[str]:
        for word in f"You said: {text}".split(" "):
            yield word + " "
