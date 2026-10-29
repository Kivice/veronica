"""Veronica Intelligence & AI Backend Engine.
Provides modular multi-provider streaming, intent classification, circuit breakers,
conversation context management, and desktop tool automation.
"""
from .adapters import (
    AnthropicAdapter,
    BaseModelAdapter,
    GeminiAdapter,
    GroqAdapter,
    OllamaAdapter,
    OpenAiAdapter,
    TacticalCoreAdapter,
)
from .circuit_breaker import CircuitBreaker
from .context import ContextManager
from .engine import IntelligenceEngine
from .intent import IntentRouter
from .models import CircuitState, IntentAnalysis, IntentType, ModelMessage, StreamChunk
from .tools_schema import TOOL_SCHEMAS, dispatch_tool_call
from .vision import VisionEngine

__all__ = [
    "IntelligenceEngine",
    "BaseModelAdapter",
    "GroqAdapter",
    "OpenAiAdapter",
    "GeminiAdapter",
    "AnthropicAdapter",
    "OllamaAdapter",
    "TacticalCoreAdapter",
    "CircuitBreaker",
    "CircuitState",
    "ContextManager",
    "IntentRouter",
    "IntentType",
    "IntentAnalysis",
    "ModelMessage",
    "StreamChunk",
    "TOOL_SCHEMAS",
    "dispatch_tool_call",
    "VisionEngine",
]
