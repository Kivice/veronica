"""Anthropic Claude inference adapter."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Optional

import httpx

from .base import BaseModelAdapter

logger = logging.getLogger("veronica.intelligence.adapters.anthropic")


class AnthropicAdapter(BaseModelAdapter):
    """Anthropic Claude 3.5 Sonnet streaming adapter."""

    def __init__(self, api_key: str = "", model: str = "claude-3-5-sonnet-20241022"):
        super().__init__(
            name="Anthropic Claude",
            provider_id="anthropic",
            default_model=model,
            api_key=api_key,
            timeout_s=12.0,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if not self.is_configured:
            raise RuntimeError("Anthropic API key not configured")

        target_model = model or self.default_model
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": target_model,
            "system": system_prompt,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 512),
            "stream": True,
        }

        start_time = time.time()
        first_token = True
        token_count = 0

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                async with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure()
                        if resp.status_code in (401, 403):
                            self.mark_key_invalid(f"Anthropic rejected API key (HTTP {resp.status_code})")
                        raise RuntimeError(f"Anthropic error HTTP {resp.status_code}: {resp.reason_phrase}")

                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("type") == "content_block_delta":
                                    delta = data.get("delta", {}).get("text", "")
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
            logger.warning("Anthropic stream error: %s", exc)
            raise
