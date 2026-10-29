"""Model adapters for multi-provider intelligence routing."""
from .anthropic import AnthropicAdapter
from .base import BaseModelAdapter
from .gemini import GeminiAdapter
from .groq import GroqAdapter
from .ollama import OllamaAdapter
from .openai import OpenAiAdapter
from .tactical_core import TacticalCoreAdapter

__all__ = [
    "BaseModelAdapter",
    "GroqAdapter",
    "OpenAiAdapter",
    "GeminiAdapter",
    "AnthropicAdapter",
    "OllamaAdapter",
    "TacticalCoreAdapter",
]
