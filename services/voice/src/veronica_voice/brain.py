"""Veronica Multi-Model Intelligence Engine.
Features an automatic fallback chain across cloud model APIs (Groq, OpenAI, Gemini, Anthropic),
local Ollama, and a built-in Tactical Offline Engine with tool execution.

Powered by the modular veronica_voice.intelligence engine subsystem.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable, Optional

from .intelligence import IntelligenceEngine

logger = logging.getLogger("veronica.brain")


class VeronicaBrain:
    """Multi-provider intelligence engine with streaming responses and real tool automation.
    Wraps the modular IntelligenceEngine for backward compatibility and clean architecture.
    """

    def __init__(self, env_path: Optional[str] = None):
        self.engine = IntelligenceEngine(env_path=env_path)

    @property
    def groq_api_key(self) -> str:
        return self.engine.groq.api_key

    @groq_api_key.setter
    def groq_api_key(self, val: str) -> None:
        self.engine.groq.update_key(val)

    @property
    def openai_api_key(self) -> str:
        return self.engine.openai.api_key

    @openai_api_key.setter
    def openai_api_key(self, val: str) -> None:
        self.engine.openai.update_key(val)
        self.engine.vision.update_keys(openai_key=val)

    @property
    def gemini_api_key(self) -> str:
        return self.engine.gemini.api_key

    @gemini_api_key.setter
    def gemini_api_key(self, val: str) -> None:
        self.engine.gemini.update_key(val)
        self.engine.vision.update_keys(gemini_key=val)

    @property
    def anthropic_api_key(self) -> str:
        return self.engine.anthropic.api_key

    @anthropic_api_key.setter
    def anthropic_api_key(self, val: str) -> None:
        self.engine.anthropic.update_key(val)

    @property
    def ollama_url(self) -> str:
        return self.engine.ollama.api_key

    @ollama_url.setter
    def ollama_url(self, val: str) -> None:
        self.engine.ollama.update_key(val)

    @property
    def conversation_history(self) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.engine.context.history]

    @conversation_history.setter
    def conversation_history(self, history: list[dict[str, str]]) -> None:
        self.engine.context.clear()
        for item in history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role == "assistant":
                self.engine.context.add_assistant_message(content)
            else:
                self.engine.context.add_user_message(content)

    @property
    def tool_callback(self) -> Optional[Callable[[str, dict[str, Any]], Any]]:
        return self.engine.tool_callback

    @tool_callback.setter
    def tool_callback(self, cb: Optional[Callable[[str, dict[str, Any]], Any]]) -> None:
        self.engine.set_tool_callback(cb)

    def set_tool_callback(self, callback: Optional[Callable[[str, dict[str, Any]], Any]]) -> None:
        """Register a callback invoked when tools or directives are executed."""
        self.engine.set_tool_callback(callback)

    def update_keys(self, keys: dict[str, str], overwrite_existing: bool = True) -> None:
        """Dynamically update API credentials from client settings and persist to disk."""
        self.engine.update_credentials(keys, overwrite_existing=overwrite_existing)

    def get_active_provider(self) -> str:
        """Determine which intelligence provider is currently primary."""
        return self.engine.get_active_provider()

    async def respond(self, user_text: str) -> AsyncIterator[str]:
        """Main entry point: streams response chunks using the best available engine."""
        async for chunk in self.engine.stream_reply(user_text):
            yield chunk

    async def analyze_screen(self, image_base64: str, prompt: str = "") -> AsyncIterator[str]:
        """Analyze a screen snapshot using multimodal cloud vision or tactical inspection."""
        async for chunk in self.engine.analyze_screen(image_base64, prompt=prompt):
            yield chunk

    def get_status(self) -> dict[str, Any]:
        """Get diagnostic status of the intelligence backend."""
        return self.engine.get_engine_status()
