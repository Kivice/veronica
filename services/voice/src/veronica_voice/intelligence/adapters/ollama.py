"""Local Ollama instance inference adapter."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Optional

import httpx

from .base import BaseModelAdapter

logger = logging.getLogger("veronica.intelligence.adapters.ollama")


class OllamaAdapter(BaseModelAdapter):
    """Local Ollama instance adapter for offline local LLMs (e.g., Llama 3.2, Qwen 2.5)."""

    def __init__(self, base_url: str = "", model: str = "llama3.2:latest"):
        super().__init__(
            name="Local Ollama",
            provider_id="ollama",
            default_model=model,
            api_key=base_url,
            timeout_s=3.0,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def base_url(self) -> str:
        return self.api_key.rstrip("/")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        target_model = model or self.default_model

        # Build prompt from messages
        prompt_lines = []
        if system_prompt:
            prompt_lines.append(f"System: {system_prompt}")
        for m in messages:
            role = m["role"].capitalize()
            prompt_lines.append(f"{role}: {m['content']}")
        prompt_lines.append("Veronica:")
        full_prompt = "\n".join(prompt_lines)

        payload = {
            "model": target_model,
            "prompt": full_prompt,
            "stream": True,
        }

        start_time = time.time()
        first_token = True
        token_count = 0

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        self.circuit_breaker.record_failure()
                        raise RuntimeError(f"Ollama returned HTTP {resp.status_code}")

                    async for line in resp.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                text_chunk = data.get("response", "")
                                if text_chunk:
                                    if first_token:
                                        ttft_ms = (time.time() - start_time) * 1000
                                        first_token = False
                                        self.circuit_breaker.record_success(ttft_ms)
                                    token_count += 1
                                    yield text_chunk
                                if data.get("done"):
                                    break
                            except Exception:
                                continue

            self.circuit_breaker.record_success(
                (time.time() - start_time) * 1000 if first_token else 0.0,
                token_count,
            )
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.debug("Ollama unavailable or timed out: %s", exc)
            raise
