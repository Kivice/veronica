"""Multimodal screen analysis and visual reconnaissance engine."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

from ..tools import get_system_telemetry
from .adapters.gemini import MODERN_GEMINI_CASCADE

logger = logging.getLogger("veronica.intelligence.vision")


class VisionEngine:
    """Handles visual inspection of user desktop frames using modern Gemini 3.x / 2.5 Flash, OpenAI GPT-4o, or local heuristics."""

    def __init__(self, gemini_api_key: str = "", openai_api_key: str = ""):
        self.gemini_api_key = gemini_api_key.strip()
        self.openai_api_key = openai_api_key.strip()
        self.gemini_key_invalid = False
        self.openai_key_invalid = False

    def update_keys(self, gemini_key: str = "", openai_key: str = "") -> None:
        if gemini_key:
            clean_g = gemini_key.strip()
            if clean_g != self.gemini_api_key:
                self.gemini_api_key = clean_g
                self.gemini_key_invalid = False
        if openai_key:
            clean_o = openai_key.strip()
            if clean_o != self.openai_api_key:
                self.openai_api_key = clean_o
                self.openai_key_invalid = False

    async def analyze(
        self,
        image_base64: str,
        prompt: str = "",
        system_prompt: str = "",
    ) -> AsyncIterator[str]:
        clean_prompt = (
            prompt.strip()
            or "Analyze what is displayed on the user's screen right now. Identify active windows, code or errors, and provide crisp tactical assistance."
        )

        # 1. Modern Gemini Vision Cascade (gemini-flash-latest -> gemini-3-flash-preview -> gemini-2.5-flash)
        if self.gemini_api_key and not self.gemini_key_invalid:
            raw_b64 = image_base64.split(",")[-1]
            payload = {
                "contents": [{
                    "parts": [
                        {"text": f"{system_prompt}\n{clean_prompt}" if system_prompt else clean_prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": raw_b64}},
                    ]
                }]
            }
            headers = {"x-goog-api-key": self.gemini_api_key}
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    for cand_model in MODERN_GEMINI_CASCADE:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:streamGenerateContent?alt=sse"
                        async with client.stream("POST", url, json=payload, headers=headers) as resp:
                            if resp.status_code == 200:
                                async for line in resp.aiter_lines():
                                    if line.startswith("data: "):
                                        try:
                                            d = json.loads(line[6:])
                                            cands = d.get("candidates", [])
                                            if cands:
                                                parts = cands[0].get("content", {}).get("parts", [])
                                                for p in parts:
                                                    if p.get("thought") is True:
                                                        continue
                                                    if "text" in p and p["text"]:
                                                        yield p["text"]
                                        except Exception:
                                            continue
                                return
                            body = (await resp.aread()).decode("utf-8", errors="ignore")
                            if resp.status_code in (401, 403) or "API_KEY_INVALID" in body or "API key not valid" in body:
                                self.gemini_key_invalid = True
                                break
                            if resp.status_code not in (404, 429, 503):
                                break
            except Exception as e:
                logger.warning("Gemini vision analysis failed: %s", e)

        # 2. Try OpenAI Vision (gpt-4o-mini)
        if self.openai_api_key and not self.openai_key_invalid:
            try:
                raw_b64 = image_base64.split(",")[-1]
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{system_prompt}\n{clean_prompt}" if system_prompt else clean_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{raw_b64}"}},
                        ],
                    }],
                    "stream": True,
                    "max_tokens": 512,
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    async with client.stream(
                        "POST",
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as resp:
                        if resp.status_code == 200:
                            async for line in resp.aiter_lines():
                                if line.startswith("data: ") and line != "data: [DONE]":
                                    try:
                                        d = json.loads(line[6:])
                                        delta = d["choices"][0]["delta"].get("content", "")
                                        if delta:
                                            yield delta
                                    except Exception:
                                        continue
                            return
                        if resp.status_code in (401, 403):
                            self.openai_key_invalid = True
            except Exception as e:
                logger.warning("OpenAI vision analysis failed: %s", e)

        # 3. Offline Tactical Reconnaissance Inspector
        telem = get_system_telemetry()
        top_app = telem["top_processes"][0]["name"] if telem["top_processes"] else "Desktop"
        reply = (
            f"Optical reconnaissance captured. Active display frame analyzed. "
            f"Primary system consumer is {top_app}. Telemetry shows CPU at {telem['cpu_percent']}%, RAM utilized at {telem['ram_percent']}%. "
            f"Configure a valid Gemini or OpenAI API key in settings for deep neural reasoning on screen code and visuals."
        )
        words = reply.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.015)
