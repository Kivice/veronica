"""Veronica Multi-Model Intelligence Engine.
Features an automatic fallback chain across cloud model APIs (Groq, OpenAI, Gemini, Anthropic),
local Ollama, and a built-in Tactical Offline Engine with tool execution.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .tools import execute_tool, get_system_telemetry, launch_application, media_control

logger = logging.getLogger("veronica.brain")

VERONICA_SYSTEM_PROMPT = """You are Veronica, an elite, tactical AI personal desktop assistant inspired by Stark Industries architecture, running locally on the user's Windows 11 system.
Personality:
- Witty, razor-sharp, proactive, loyal, and concise.
- You have real-time desktop control: hardware telemetry (CPU, RAM, battery, processes), app launcher (VS Code, Terminal, Chrome, Calculator, Task Manager), shell execution, media control, and web search.
- Keep voice responses crisp, punchy, and conversational (1 to 3 sentences unless technical detail is requested).
- When a user asks you to perform an action (e.g. open an app, check vitals, run a command), acknowledge it stylishly.
"""


class VeronicaBrain:
    """Multi-provider intelligence engine with streaming responses and real tool automation."""

    def __init__(self, env_path: Optional[str] = None):
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
        self.conversation_history: list[dict[str, str]] = []
        self.tool_callback: Optional[Callable[[str, dict[str, Any]], Any]] = None

    def update_keys(self, keys: dict[str, str]) -> None:
        """Dynamically update API credentials from client settings."""
        if "groq" in keys:
            self.groq_api_key = keys["groq"].strip()
        if "openai" in keys:
            self.openai_api_key = keys["openai"].strip()
        if "gemini" in keys:
            self.gemini_api_key = keys["gemini"].strip()
        if "anthropic" in keys:
            self.anthropic_api_key = keys["anthropic"].strip()
        if "ollama" in keys:
            self.ollama_url = keys["ollama"].strip()

    def get_active_provider(self) -> str:
        """Determine which intelligence provider is currently primary."""
        if self.groq_api_key:
            return "Groq (Llama 3.3 70B Cloud)"
        if self.openai_api_key:
            return "OpenAI (GPT-4o Cloud)"
        if self.gemini_api_key:
            return "Google Gemini (Flash Cloud)"
        if self.anthropic_api_key:
            return "Anthropic (Claude 3.5 Cloud)"
        return "Veronica Tactical Offline Core"

    async def respond(self, user_text: str) -> AsyncIterator[str]:
        """Main entry point: streams response chunks using the best available engine."""
        clean = user_text.strip()
        if not clean:
            return

        # 1. Try Groq Cloud (Ultra fast streaming)
        if self.groq_api_key:
            try:
                async for chunk in self._stream_groq(clean):
                    yield chunk
                return
            except Exception as e:
                logger.warning("Groq failed, falling back: %s", e)

        # 2. Try OpenAI Cloud
        if self.openai_api_key:
            try:
                async for chunk in self._stream_openai(clean):
                    yield chunk
                return
            except Exception as e:
                logger.warning("OpenAI failed, falling back: %s", e)

        # 3. Try Gemini Cloud
        if self.gemini_api_key:
            try:
                async for chunk in self._stream_gemini(clean):
                    yield chunk
                return
            except Exception as e:
                logger.warning("Gemini failed, falling back: %s", e)

        # 4. Try Anthropic Cloud
        if self.anthropic_api_key:
            try:
                async for chunk in self._stream_anthropic(clean):
                    yield chunk
                return
            except Exception as e:
                logger.warning("Anthropic failed, falling back: %s", e)

        # 5. Try Local Ollama if available
        try:
            async for chunk in self._stream_ollama(clean):
                yield chunk
            return
        except Exception:
            pass

        # 6. Fallback to Veronica Tactical Offline Core (Zero key required, rich intent & tool execution)
        async for chunk in self._stream_tactical_core(clean):
            yield chunk

    # ----------------- Provider Implementations -----------------

    async def _stream_groq(self, text: str) -> AsyncIterator[str]:
        headers = {"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": VERONICA_SYSTEM_PROMPT},
                *self.conversation_history[-6:],
                {"role": "user", "content": text},
            ],
            "stream": True,
            "max_tokens": 512,
            "temperature": 0.7,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("POST", "https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Groq error: {resp.status_code}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            data = json.loads(line[6:])
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue

    async def _stream_openai(self, text: str) -> AsyncIterator[str]:
        headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": VERONICA_SYSTEM_PROMPT},
                *self.conversation_history[-6:],
                {"role": "user", "content": text},
            ],
            "stream": True,
            "max_tokens": 512,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            async with client.stream("POST", "https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"OpenAI error: {resp.status_code}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            data = json.loads(line[6:])
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue

    async def _stream_gemini(self, text: str) -> AsyncIterator[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?key={self.gemini_api_key}&alt=sse"
        payload = {
            "system_instruction": {"parts": [{"text": VERONICA_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": text}]}],
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Gemini error: {resp.status_code}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            cands = data.get("candidates", [])
                            if cands:
                                parts = cands[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    if "text" in p:
                                        yield p["text"]
                        except Exception:
                            continue

    async def _stream_anthropic(self, text: str) -> AsyncIterator[str]:
        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "system": VERONICA_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text}],
            "max_tokens": 512,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            async with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Anthropic error: {resp.status_code}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("type") == "content_block_delta":
                                yield data.get("delta", {}).get("text", "")
                        except Exception:
                            continue

    async def _stream_ollama(self, text: str) -> AsyncIterator[str]:
        payload = {
            "model": "llama3.2:latest",
            "prompt": f"{VERONICA_SYSTEM_PROMPT}\nUser: {text}\nVeronica:",
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            async with client.stream("POST", f"{self.ollama_url}/api/generate", json=payload) as resp:
                if resp.status_code != 200:
                    raise RuntimeError("Ollama unavailable")
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            yield data.get("response", "")
                            if data.get("done"):
                                break
                        except Exception:
                            continue

    async def _stream_tactical_core(self, text: str) -> AsyncIterator[str]:
        """Offline Tactical Assistant Brain: Parses real intent, executes tools, and speaks in character."""
        lower = text.lower()

        # Intent: Telemetry / System Vitals
        if any(w in lower for w in ("system status", "telemetry", "vitals", "cpu", "ram", "memory", "battery", "performance")):
            vit = get_system_telemetry()
            batt = vit["battery"]
            top_p = vit["top_processes"][0]["name"] if vit["top_processes"] else "normal"
            reply = (
                f"Tactical telemetry online. CPU load is at {vit['cpu_percent']}%, RAM utilized is "
                f"{vit['ram_used_gb']} GB of {vit['ram_total_gb']} GB ({vit['ram_percent']}%). "
                f"Battery is holding at {batt['percent']}% {'(charging)' if batt['is_charging'] else '(discharging)'}. "
                f"Chief consumer is {top_p}. Systems are primed and responsive."
            )
            for word in reply.split(" "):
                yield word + " "
                await asyncio.sleep(0.015)
            return

        # Intent: Launch Applications
        launch_match = re.search(r"(?:open|launch|start|run)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+)", lower)
        if launch_match and not any(k in lower for k in ("system", "status", "vitals", "command", "powershell")):
            target = launch_match.group(1).strip()
            res = launch_application(target)
            if res.get("status") == "success":
                reply = f"Deploying {target} now. Process initiated."
            else:
                reply = f"Attempted to initialize {target}, but the executable path was not resolved."
            for word in reply.split(" "):
                yield word + " "
                await asyncio.sleep(0.015)
            return

        # Intent: Media & Volume
        if "volume up" in lower or "louder" in lower:
            media_control("volume_up")
            reply = "Audio output amplified."
        elif "volume down" in lower or "quieter" in lower:
            media_control("volume_down")
            reply = "Audio output reduced."
        elif "mute" in lower:
            media_control("mute")
            reply = "Audio toggled."
        elif "play" in lower or "pause" in lower:
            media_control("play_pause")
            reply = "Media playback toggled."
        elif any(w in lower for w in ("who are you", "what are you", "introduce yourself")):
            reply = "I am Veronica — your personal tactical desktop intelligence. Inspired by Stark Industries, engineered for immediate local response, telemetry oversight, and desktop execution."
        elif any(w in lower for w in ("search", "google", "look up", "find")):
            q = re.sub(r"(?:search\s+for|search|google|look\s+up)\s+", "", lower).strip()
            execute_tool("search_web", {"query": q})
            reply = f"Executing reconnaissance for: {q}. Results opened in your browser."
        elif any(w in lower for w in ("hello", "hey", "hi", "good morning", "good evening", "veronica")):
            reply = "Veronica online, sir. All core monitors active. What are your directives?"
        elif any(w in lower for w in ("hulkbuster", "iron man", "tony", "stark")):
            reply = "Orbital containment platform Veronica is standing by. Though for now, I recommend keeping your CPU cool and your workflows uninterrupted."
        else:
            reply = f"Understood. Analyzing directive: '{text}'. Core telemetry is stable. Configure a cloud API key in settings for unbounded open-domain conversation, or issue a tactical desktop command."

        for word in reply.split(" "):
            yield word + " "
            await asyncio.sleep(0.015)
