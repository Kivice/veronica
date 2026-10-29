"""Google Gemini Modern Pipeline Adapter (Gemini 3.x / 2.5 Flash & Pro with Auto-Discovery)."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, AsyncIterator, Optional

import httpx

from .base import BaseModelAdapter

logger = logging.getLogger("veronica.intelligence.adapters.gemini")

# Ordered modern fallback cascade:
# 1. gemini-flash-latest (Google's official dynamic pointer to the newest GA Flash model, e.g. Gemini 3.x / 2.5 Flash)
# 2. gemini-3-flash-preview / gemini-2.5-flash (explicit modern hybrid-reasoning Flash models)
# 3. gemini-2.5-flash-lite (ultra-low-latency high-throughput fallback)
# 4. gemini-2.5-pro (deep reasoning fallback)
MODERN_GEMINI_CASCADE = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]


class GeminiAdapter(BaseModelAdapter):
    """Modern Google Gemini streaming adapter supporting Gemini 3.x / 2.5 Flash & Pro,
    thought-part filtering for thinking models, and live model auto-discovery.
    """

    def __init__(self, api_key: str = "", model: str = "gemini-3-flash-preview"):
        super().__init__(
            name="Google Gemini Flash",
            provider_id="gemini",
            default_model=model,
            api_key=api_key,
            timeout_s=15.0,
        )
        self._discovered_models: list[str] = []

    def update_key(self, key: str) -> None:
        clean = key.strip()
        if clean == self.api_key and self.key_invalid:
            # Ignore redundant re-sync of an already-known invalid key (e.g. from browser localStorage)
            return
        super().update_key(clean)
        self._discovered_models = []

    async def _discover_best_models(self, client: httpx.AsyncClient) -> list[str]:
        """Query the v1beta models endpoint once per key to discover the newest Flash/Pro models enabled for this key."""
        if self._discovered_models:
            return self._discovered_models
        try:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                headers={"x-goog-api-key": self.api_key},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            candidates: list[str] = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue
                name = m.get("name", "").replace("models/", "")
                if not name.startswith("gemini-") or "embedding" in name or "imagen" in name or "tts" in name or "veo" in name:
                    continue
                candidates.append(name)

            # Rank higher version numbers & flash models first for low-latency voice interaction
            def _score(model_id: str) -> tuple[int, float, int]:
                ver_match = re.search(r"gemini-(\d+(?:\.\d+)?)", model_id)
                ver = float(ver_match.group(1)) if ver_match else 2.0
                is_flash = 2 if "flash" in model_id and "lite" not in model_id else (1 if "flash" in model_id else 0)
                is_stable = 0 if "exp" in model_id else 1
                return (is_Flash := is_flash, ver, is_stable)

            candidates.sort(key=_score, reverse=True)
            self._discovered_models = candidates[:6]
            return self._discovered_models
        except Exception:
            return []

    def _build_candidate_list(self, requested: Optional[str]) -> list[str]:
        target_models: list[str] = []
        for m in [requested or self.default_model, *self._discovered_models, *MODERN_GEMINI_CASCADE]:
            if m and m not in target_models:
                target_models.append(m)
        return target_models

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if not self.is_configured:
            raise RuntimeError("Gemini API key not configured")

        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        tool_declarations = kwargs.get("tools")
        tool_executor = kwargs.get("tool_executor")
        max_tool_rounds = int(kwargs.get("max_tool_rounds", 4))

        target_models = self._build_candidate_list(model)
        last_err: Optional[str] = None
        start_time = time.time()
        first_token = True
        token_count = 0
        tried_discovery = False

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            idx = 0
            while idx < len(target_models):
                cand_model = target_models[idx]
                idx += 1
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:streamGenerateContent?alt=sse"
                headers = {"x-goog-api-key": self.api_key}

                try:
                    round_num = 0
                    while round_num <= max_tool_rounds:
                        round_num += 1
                        payload: dict[str, Any] = {"contents": contents}
                        if system_prompt:
                            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
                        if tool_declarations and callable(tool_executor) and round_num <= max_tool_rounds:
                            payload["tools"] = [{"functionDeclarations": tool_declarations}]

                        model_turn_parts: list[dict[str, Any]] = []
                        pending_fn_calls: list[dict[str, Any]] = []

                        async with client.stream("POST", url, json=payload, headers=headers) as resp:
                            if resp.status_code == 200:
                                async for line in resp.aiter_lines():
                                    if line.startswith("data: "):
                                        try:
                                            data = json.loads(line[6:])
                                            cands = data.get("candidates", [])
                                            if cands:
                                                parts = cands[0].get("content", {}).get("parts", [])
                                                for p in parts:
                                                    model_turn_parts.append(p)
                                                    if "functionCall" in p:
                                                        pending_fn_calls.append(p["functionCall"])
                                                        continue
                                                    # Skip internal reasoning/thought blocks on Gemini 2.5+ / 3.x thinking models
                                                    if p.get("thought") is True:
                                                        continue
                                                    if "text" in p and p["text"]:
                                                        if first_token:
                                                            ttft_ms = (time.time() - start_time) * 1000
                                                            first_token = False
                                                            self.circuit_breaker.record_success(ttft_ms)
                                                        token_count += 1
                                                        yield p["text"]
                                        except Exception:
                                            continue

                                # If Gemini invoked one or more agentic tools, execute them and continue the ReAct loop
                                if pending_fn_calls and callable(tool_executor):
                                    contents.append({"role": "model", "parts": model_turn_parts})
                                    fn_response_parts: list[dict[str, Any]] = []
                                    for fc in pending_fn_calls:
                                        fn_name = fc.get("name", "")
                                        fn_args = fc.get("args") or {}
                                        res = tool_executor(fn_name, fn_args)
                                        fn_response_parts.append({
                                            "functionResponse": {
                                                "name": fn_name,
                                                "response": {"result": res},
                                            }
                                        })
                                    contents.append({"role": "user", "parts": fn_response_parts})
                                    continue

                                self.circuit_breaker.record_success(
                                    (time.time() - start_time) * 1000 if first_token else 0.0,
                                    token_count,
                                )
                                self.default_model = cand_model
                                return

                            body = (await resp.aread()).decode("utf-8", errors="ignore")
                            last_err = f"Gemini {cand_model} HTTP {resp.status_code}"
                            if resp.status_code in (401, 403) or "API_KEY_INVALID" in body or "API key not valid" in body:
                                self.mark_key_invalid("Gemini rejected API key (API_KEY_INVALID)")
                                break
                            if resp.status_code == 404 and not tried_discovery:
                                tried_discovery = True
                                discovered = await self._discover_best_models(client)
                                for dm in discovered:
                                    if dm not in target_models:
                                        target_models.append(dm)
                                break
                            if resp.status_code not in (404, 429, 503):
                                break
                            break
                    if self.key_invalid:
                        break
                except Exception as e:
                    last_err = str(e)
                    continue

        self.circuit_breaker.record_failure()
        logger.warning("Gemini failed across models: %s", last_err)
        raise RuntimeError(f"Gemini provider error: {last_err}")
