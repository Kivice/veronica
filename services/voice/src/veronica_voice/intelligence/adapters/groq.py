"""Groq Cloud low-latency inference adapter."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Optional

import httpx

from .base import BaseModelAdapter

logger = logging.getLogger("veronica.intelligence.adapters.groq")


class GroqAdapter(BaseModelAdapter):
    """Ultra-fast Llama 3.3 70B & 8B streaming via Groq LPUs."""

    def __init__(self, api_key: str = "", model: str = "llama-3.3-70b-versatile"):
        super().__init__(
            name="Groq Cloud LPU",
            provider_id="groq",
            default_model=model,
            api_key=api_key,
            timeout_s=10.0,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if not self.is_configured:
            raise RuntimeError("Groq API key not configured")

        target_model = model or self.default_model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload_messages = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)

        payload = {
            "model": target_model,
            "messages": payload_messages,
            "stream": True,
            "max_tokens": kwargs.get("max_tokens", 512),
            "temperature": kwargs.get("temperature", 0.7),
        }

        start_time = time.time()
        first_token = True
        token_count = 0

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                async with client.stream(
                    "POST",
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure()
                        if resp.status_code in (401, 403):
                            self.mark_key_invalid(f"Groq rejected API key (HTTP {resp.status_code})")
                        raise RuntimeError(f"Groq API error HTTP {resp.status_code}: {resp.reason_phrase}")

                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                data = json.loads(line[6:])
                                delta = data["choices"][0]["delta"].get("content", "")
                                if delta:
                                    if first_token:
                                        ttft_ms = (time.time() - start_time) * 1000
                                        first_token = False
                                        self.circuit_breaker.record_success(ttft_ms)
                                    token_count += 1
                                    yield delta
                            except Exception:
                                continue

            self.circuit_breaker.record_success(
                (time.time() - start_time) * 1000 if first_token else 0.0,
                token_count,
            )
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.warning("Groq stream error: %s", exc)
            raise
