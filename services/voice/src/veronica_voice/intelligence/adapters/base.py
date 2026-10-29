"""Base class and interface contract for all Veronica AI model adapters."""
from __future__ import annotations

import abc
import time
from typing import Any, AsyncIterator, Optional

from ..circuit_breaker import CircuitBreaker


class BaseModelAdapter(abc.ABC):
    """Abstract base adapter for neural LLM streaming backends."""

    def __init__(
        self,
        name: str,
        provider_id: str,
        default_model: str,
        api_key: str = "",
        timeout_s: float = 12.0,
    ):
        self.name = name
        self.provider_id = provider_id
        self.default_model = default_model
        self.api_key = api_key.strip()
        self.timeout_s = timeout_s
        self.circuit_breaker = CircuitBreaker(name=self.name)
        # Set when the provider rejects the credential (HTTP 401/403 or API_KEY_INVALID).
        # The adapter is skipped until a new key is supplied.
        self.key_invalid = False
        self.last_error = ""

    @property
    def is_available(self) -> bool:
        """Adapter is available if it has credentials (or is local/offline) and its circuit is not tripped."""
        return self.is_configured and not self.key_invalid and self.circuit_breaker.can_execute()

    @property
    def is_configured(self) -> bool:
        """Whether the adapter has the necessary key or URL."""
        return bool(self.api_key)

    def mark_key_invalid(self, detail: str) -> None:
        self.key_invalid = True
        self.last_error = detail

    def update_key(self, key: str) -> None:
        self.api_key = key.strip()
        self.key_invalid = False
        self.last_error = ""
        if self.api_key:
            self.circuit_breaker.reset()

    @abc.abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream response text tokens for a given message history and system prompt."""
        ...

    async def respond(self, text: str) -> AsyncIterator[str]:
        """Implements the LlmAdapter protocol interface."""
        messages = [{"role": "user", "content": text}]
        async for chunk in self.stream_chat(messages, system_prompt=""):
            yield chunk

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider_id": self.provider_id,
            "model": self.default_model,
            "configured": self.is_configured,
            "available": self.is_available,
            "key_invalid": self.key_invalid,
            "last_error": self.last_error,
            "circuit": self.circuit_breaker.state.value,
            "metrics": self.circuit_breaker.metrics.to_dict(),
        }
