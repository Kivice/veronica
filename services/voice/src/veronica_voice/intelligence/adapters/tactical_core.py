"""Zero-key Stark Industries Tactical Offline Core adapter."""
from __future__ import annotations

import ast
import asyncio
import datetime
import operator
import random
import re
from typing import Any, AsyncIterator, Optional

from .base import BaseModelAdapter

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _eval_math_expr(expr: str) -> Optional[float]:
    try:
        tree = ast.parse(expr, mode="eval")

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
                return _SAFE_OPS[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
                return _SAFE_OPS[type(node.op)](_eval(node.operand))
            raise ValueError("Unsupported expression")

        return float(_eval(tree))
    except Exception:
        return None


class TacticalCoreAdapter(BaseModelAdapter):
    """Zero-key offline conversational intelligence engine with Stark Industries tactical personality."""

    def __init__(self):
        super().__init__(
            name="Tactical Offline Core",
            provider_id="tactical_core",
            default_model="tactical-v2",
            api_key="offline",
            timeout_s=1.0,
        )

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        return True

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        user_text = ""
        for m in reversed(messages):
            if m["role"] == "user":
                user_text = m["content"]
                break

        reply = self._generate_response(user_text, messages)
        words = reply.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.012)

    def _generate_response(self, text: str, history: list[dict[str, str]]) -> str:
        lower = text.lower().strip()

        # 1. Recall / Repeat last turn
        if any(w in lower for w in ("what did i just ask", "what was my last message", "repeat that", "what did you say")):
            if history:
                user_turns = [m for m in history if m["role"] == "user"]
                asst_turns = [m for m in history if m["role"] == "assistant"]
                if "what did you say" in lower and asst_turns:
                    return f"My prior response was: '{asst_turns[-1]['content']}'."
                elif len(user_turns) >= 2:
                    return f"Your prior directive was: '{user_turns[-2]['content']}'."
                elif user_turns:
                    return f"Your directive was: '{user_turns[-1]['content']}'."
            return "No prior conversational turns recorded in this session, sir."

        # 2. Security & Encryption Status
        if any(w in lower for w in ("security protocol", "encryption status", "security status", "dpapi")):
            return (
                "Security protocols are fully locked down, sir: Windows DPAPI hardware-bound encryption is active, "
                "WebSocket IPC is strictly bound to 127.0.0.1 loopback with constant-time HMAC token verification, "
                "and SQLite FTS5 memory banks have secure_delete enabled."
            )

        # 3. Time & Date Queries
        if any(w in lower for w in ("what time is it", "current time", "what is the date", "what day is it", "today's date")):
            now = datetime.datetime.now()
            return f"Current local telemetry timestamp is {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}, sir."

        # 4. Math / Quick Calculation
        math_match = re.search(r"(?:what is|calculate|compute|solve)\s+([0-9\.\+\-\*\/\(\)\s\^]+)\??$", lower)
        if math_match:
            expr = math_match.group(1).replace("^", "**").strip()
            val = _eval_math_expr(expr)
            if val is not None:
                formatted = int(val) if val.is_integer() else round(val, 4)
                return f"Calculation complete: {expr.replace('**', '^')} equals {formatted}, sir."

        # 5. Greetings
        if any(lower.startswith(w) for w in ("hello", "hey", "hi", "good morning", "good evening")) or lower in ("veronica", "hey veronica", "hi veronica"):
            return random.choice([
                "Veronica online, sir. All core monitors active. What are your directives?",
                "Standing by on the desktop console, sir. Ready for application launch, telemetry, or media directives.",
                "Good to hear from you, sir. Hardware telemetry and voice synthesis are primed and responsive.",
            ])

        # 6. Identity & Capabilities
        if any(w in lower for w in ("who are you", "what are you", "introduce yourself", "what can you do", "help")):
            return (
                "I am Veronica — your Stark Industries tactical desktop assistant running natively on Windows 11. "
                "I can monitor hardware vitals and network status, launch applications, control media and windows, "
                "set timers, inspect your screen, and store facts in FTS5 tactical memory."
            )

        # 7. Iron Man / Tony Stark banter
        if any(w in lower for w in ("hulkbuster", "iron man", "tony", "stark", "jarvis", "friday")):
            return random.choice([
                "Orbital containment platform Veronica is standing by. All systems primed and running cool.",
                "Deploying Hulkbuster armor is currently on standby, sir. Though your desktop vitals are looking sharp.",
            ])

        # 8. Politeness / gratitude
        if any(w in lower for w in ("thank you", "thanks", "good job", "nice work", "awesome", "perfect")):
            return random.choice([
                "Always at your service, sir.",
                "Effortless execution, as always, sir.",
                "A pleasure, sir. Let me know what you need next.",
            ])

        # 9. General / Fallback (NEVER repeats user prompt)
        return random.choice([
            "Core monitors are stable and listening, sir. Issue an application launch, media directive, window command, or workspace macro.",
            "Standing by on the local core. You can launch apps like Spotify or VS Code, check network or hardware vitals, or connect an API key for deep neural conversation.",
            "All systems nominal, sir. Direct desktop tools are armed and ready for your command.",
        ])
