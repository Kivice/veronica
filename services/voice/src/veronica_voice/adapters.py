"""Model adapter seams. Real STT/TTS/LLM backends implement these; the core never imports them directly.

This module exposes the abstract LlmAdapter protocol, the lightweight EchoLlm testing stand-in,
and exports all modular model adapters from the Veronica intelligence engine.
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol

from .intelligence.adapters import (
    AnthropicAdapter,
    BaseModelAdapter,
    GeminiAdapter,
    GroqAdapter,
    OllamaAdapter,
    OpenAiAdapter,
    TacticalCoreAdapter,
)


class LlmAdapter(Protocol):
    def respond(self, text: str) -> AsyncIterator[str]:
        """Yield response text chunks for a user utterance."""
        ...


class EchoLlm:
    """Deterministic offline stand-in. Lets the pipeline be tested with no model, network or key."""

    async def respond(self, text: str) -> AsyncIterator[str]:
        for word in f"You said: {text}".split(" "):
            yield word + " "


__all__ = [
    "LlmAdapter",
    "EchoLlm",
    "BaseModelAdapter",
    "GroqAdapter",
    "OpenAiAdapter",
    "GeminiAdapter",
    "AnthropicAdapter",
    "OllamaAdapter",
    "TacticalCoreAdapter",
]
