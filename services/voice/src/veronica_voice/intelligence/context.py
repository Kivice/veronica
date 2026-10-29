"""Context and memory manager for conversation history, dynamic prompts, and privacy redaction."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..tools import _ensure_memory_file, get_system_telemetry
from .models import ModelMessage

logger = logging.getLogger("veronica.intelligence.context")

VERONICA_TACTICAL_SYSTEM_PROMPT = """You are Veronica, an elite tactical AI desktop assistant inspired by Stark Industries architecture, running locally on the user's Windows 11 system.
Personality & Behavior:
- Witty, razor-sharp, proactive, loyal, and concise.
- You have real-time desktop control: hardware telemetry (CPU, RAM, battery, processes), app launcher (VS Code, Terminal, Chrome, Calculator, Task Manager), shell execution, media control, and web search.
- Keep voice responses crisp, punchy, and conversational (1 to 3 sentences unless technical detail or code is explicitly requested).
- Never repeat the user's prompt verbatim. Sound in effortless command of the desktop.
- When an action or directive has been executed, acknowledge it with stylish tactical flair.
"""

# Regex patterns to detect sensitive data that should never leave the local machine
SENSITIVE_PATTERNS = [
    re.compile(r"gsk_[a-zA-Z0-9]{20,}", re.IGNORECASE),          # Groq keys
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),           # OpenAI keys
    re.compile(r"AIzaSy[a-zA-Z0-9_\-]{30,}", re.IGNORECASE),     # Google Gemini keys
    re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),    # Anthropic keys
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),# Bearer tokens
    re.compile(r"password\s*[:=]\s*[^\s,;]+", re.IGNORECASE),     # Raw passwords
]


def redact_sensitive_data(text: str) -> str:
    """Scrub sensitive credentials and secrets before transmitting to cloud models."""
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub("[REDACTED_CREDENTIAL]", redacted)
    return redacted


class ContextManager:
    """Maintains conversation turns, sliding token windows, dynamic system prompts, and privacy sanitization."""

    def __init__(self, max_history_turns: int = 16, token_budget: int = 3000):
        self.max_history_turns = max_history_turns
        self.token_budget = token_budget
        self.history: list[ModelMessage] = []

    def add_user_message(self, text: str) -> None:
        clean = text.strip()
        if clean:
            self.history.append(ModelMessage(role="user", content=clean))
            self._trim_history()

    def add_assistant_message(self, text: str) -> None:
        clean = text.strip()
        if clean:
            self.history.append(ModelMessage(role="assistant", content=clean))
            self._trim_history()

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 characters per token."""
        return max(1, len(text) // 4)

    def _trim_history(self) -> None:
        """Ensure history stays within turn count and token budget."""
        if len(self.history) > self.max_history_turns:
            self.history = self.history[-self.max_history_turns:]

        total_tokens = sum(self._estimate_tokens(m.content) for m in self.history)
        while total_tokens > self.token_budget and len(self.history) > 2:
            dropped = self.history.pop(0)
            total_tokens -= self._estimate_tokens(dropped.content)

    def build_system_prompt(self, include_vitals_alert: bool = True) -> str:
        """Construct the dynamic system prompt with stored memories and ambient vitals."""
        prompt = VERONICA_TACTICAL_SYSTEM_PROMPT

        # 1. Inject persistent long-term memories
        try:
            mem = _ensure_memory_file()
            notes = mem.get("notes", {})
            if notes:
                prompt += "\n\n[Active Long-Term Tactical Memory Banks]:\n"
                prompt += "The user has instructed you to remember the following persistent facts:\n"
                for k, v in notes.items():
                    prompt += f"- {k}: {v}\n"
                prompt += "Seamlessly incorporate these stored facts when conversing or executing directives."
        except Exception as exc:
            logger.debug("Failed reading memory file for prompt: %s", exc)

        # 2. Inject telemetry alert if system is strained
        if include_vitals_alert:
            try:
                telem = get_system_telemetry()
                cpu_load = telem.get("cpu_percent", 0)
                ram_percent = telem.get("ram_percent", 0)
                batt = telem.get("battery", {})
                is_low_batt = batt.get("has_battery") and batt.get("percent", 100) < 20 and not batt.get("is_charging")

                alerts = []
                if cpu_load > 85:
                    alerts.append(f"High CPU strain ({cpu_load}%)")
                if ram_percent > 85:
                    alerts.append(f"High RAM pressure ({ram_percent}%)")
                if is_low_batt:
                    alerts.append(f"Battery critically low ({batt.get('percent')}%)")

                if alerts:
                    prompt += f"\n\n[System Alert Advisory]: Active hardware conditions: {', '.join(alerts)}. Advise user if appropriate."
            except Exception:
                pass

        return prompt

    def get_messages_for_provider(
        self,
        new_prompt: Optional[str] = None,
        redact_secrets: bool = True,
        max_turns: int = 8,
    ) -> list[dict[str, str]]:
        """Format history messages for model consumption with optional secret redaction."""
        recent = self.history[-max_turns:]
        formatted: list[dict[str, str]] = []

        for msg in recent:
            content = redact_sensitive_data(msg.content) if redact_secrets else msg.content
            formatted.append({"role": msg.role, "content": content})

        if new_prompt:
            content = redact_sensitive_data(new_prompt) if redact_secrets else new_prompt
            formatted.append({"role": "user", "content": content})

        return formatted

    def clear(self) -> None:
        self.history.clear()
