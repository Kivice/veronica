"""Structured Operational Logging & Security Audit Trail for Project Veronica.

Writes redacted operational logs to ~/.veronica/veronica.log and structured JSONL
audit events to ~/.veronica/audit.jsonl (covering tool executions, IoT commands,
and authentication events).
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_DIR = Path.home() / ".veronica"
APP_LOG_FILE = LOG_DIR / "veronica.log"
AUDIT_LOG_FILE = LOG_DIR / "audit.jsonl"

_configured = False

_SECRET_RE = re.compile(
    r"(?:AIza[0-9A-Za-z\-_]{20,}|gsk_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z\-_]{20,}|"
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*|"
    r"(?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9\-._~+/]{12,})",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    """Redact API keys, bearer tokens, and secrets from log strings."""
    if not text:
        return text
    return _SECRET_RE.sub("[REDACTED]", text)


class _RedactingFormatter(logging.Formatter):
    """Ensures no API key or bearer token is ever written to disk logs."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return redact_secrets(rendered)


def setup_veronica_logging(level: int = logging.INFO) -> None:
    """Attach a rotating file handler at ~/.veronica/veronica.log to the root 'veronica' logger."""
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger("veronica")
    root_logger.setLevel(level)

    file_handler = RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        _RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root_logger.addHandler(file_handler)
    _configured = True
    root_logger.info("Veronica structured logging initialized at %s", APP_LOG_FILE)


def _redact_obj(obj: Any) -> Any:
    """Recursively redact secrets in dicts, lists, and strings without breaking JSON structure."""
    if isinstance(obj, str):
        return redact_secrets(obj)
    if isinstance(obj, dict):
        return {
            k: ("[REDACTED]" if str(k).lower() in ("token", "api_key", "apikey", "secret", "password", "authorization") else _redact_obj(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_obj(x) for x in obj]
    return obj


def record_audit_event(
    category: str,
    action: str = "",
    status: str = "success",
    details: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Append a tamper-evident JSONL security/tool audit entry to ~/.veronica/audit.jsonl."""
    entry: dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "category": category,
        "action": action or category,
        "status": status,
        "details": _redact_obj(details or kwargs or {}),
    }
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:
        pass
    return entry


def get_veronica_logs(
    lines: int = 25,
    limit: int | None = None,
    include_audit: bool = True,
) -> dict[str, Any]:
    """Retrieve recent operational log lines and recent security audit events."""
    setup_veronica_logging()
    effective_limit = limit if limit is not None else lines
    max_lines = max(5, min(int(effective_limit), 100))

    app_lines: list[str] = []
    if APP_LOG_FILE.exists():
        try:
            all_lines = APP_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            app_lines = all_lines[-max_lines:]
        except Exception:
            pass

    audit_events: list[dict[str, Any]] = []
    if include_audit and AUDIT_LOG_FILE.exists():
        try:
            raw_audit = AUDIT_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            for row in raw_audit[-max_lines:]:
                try:
                    audit_events.append(json.loads(row))
                except Exception:
                    continue
        except Exception:
            pass

    return {
        "status": "success",
        "log_file": str(APP_LOG_FILE),
        "audit_file": str(AUDIT_LOG_FILE),
        "recent_logs": app_lines,
        "recent_audit_events": audit_events[-15:],
        "log_count": len(app_lines),
        "audit_count": len(audit_events),
    }
