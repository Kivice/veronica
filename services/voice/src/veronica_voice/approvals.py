"""Per-action approval gate for LLM-initiated tool calls ("allow once / always / never").

Only actions the *model* decides to take are gated; direct user commands (typed/spoken fast-path
directives and HUD buttons) are explicit user intent and run without a prompt.
Decisions made with "always"/"never" persist in ~/.veronica/approvals.json and every decision is audited.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .audit_logger import record_audit_event

APPROVALS_FILE = Path.home() / ".veronica" / "approvals.json"
APPROVAL_TIMEOUT_S = 45.0

# (tool, action) combos that always need consent when the model initiates them
_HIGH_RISK_IOT = frozenset({"unlock", "lock", "disarm", "register", "remove"})
_HIGH_RISK_APP_ACTIONS = frozenset({"type", "hotkey", "send_keys"})
_HIGH_RISK_BROWSER_TABS = frozenset({"close_tab"})


def classify_risk(tool_name: str, args: dict[str, Any]) -> Optional[tuple[str, str]]:
    """Return (policy_key, human_reason) if the call needs approval, else None."""
    name = (tool_name or "").lower()
    action = str(args.get("action", "")).lower()

    if name in ("execute_command", "run_command"):
        cmd = str(args.get("command", ""))[:160]
        return "execute_command", f"Run PowerShell command: {cmd}"
    if name == "close_application" and bool(args.get("force", False)):
        return "close_application:force", f"Force-terminate {args.get('app_name') or args.get('app', 'an application')}"
    if name in ("iot_control", "iot") and action in _HIGH_RISK_IOT:
        return f"iot_control:{action}", f"IoT {action} on '{args.get('target', args.get('device', 'device'))}'"
    if name in ("app_interact", "interact_app") and action in _HIGH_RISK_APP_ACTIONS:
        return f"app_interact:{action}", f"{action.title()} '{str(args.get('content', ''))[:80]}' into {args.get('app', 'active window')}"
    if name in ("browser_agent", "browser") and action in _HIGH_RISK_BROWSER_TABS:
        return f"browser_agent:{action}", "Close the active browser tab"
    if name == "clipboard_tool" and action == "set":
        return "clipboard_tool:set", "Overwrite the system clipboard"
    return None


class ApprovalManager:
    """Tracks persisted always/never decisions and in-flight approval requests."""

    def __init__(self, path: Path = APPROVALS_FILE) -> None:
        self.path = path
        self._pending: dict[str, asyncio.Future] = {}

    # ---- persistence -------------------------------------------------
    def _load(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {"always": list(data.get("always", [])), "never": list(data.get("never", []))}
        except Exception:
            return {"always": [], "never": []}

    def _save(self, data: dict[str, list[str]]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def standing_decision(self, key: str) -> Optional[str]:
        data = self._load()
        if key in data["never"]:
            return "never"
        if key in data["always"]:
            return "always"
        return None

    def remember(self, key: str, decision: str) -> None:
        data = self._load()
        for bucket in ("always", "never"):
            if key in data[bucket]:
                data[bucket].remove(key)
        if decision in ("always", "never"):
            data[decision].append(key)
        self._save(data)

    def reset(self) -> None:
        self._save({"always": [], "never": []})

    # ---- request / response -----------------------------------------
    def resolve(self, request_id: str, decision: str) -> bool:
        fut = self._pending.get(request_id)
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True

    async def request(
        self,
        key: str,
        tool_name: str,
        reason: str,
        args: dict[str, Any],
        send: Optional[Callable[[dict[str, Any]], Awaitable[None]]],
        timeout: float = APPROVAL_TIMEOUT_S,
    ) -> bool:
        """Ask the user. Returns True if the action may proceed."""
        standing = self.standing_decision(key)
        if standing == "never":
            record_audit_event("approval", key, "denied", {"tool": tool_name, "source": "standing_never"})
            return False
        if standing == "always":
            record_audit_event("approval", key, "approved", {"tool": tool_name, "source": "standing_always"})
            return True
        if send is None:
            record_audit_event("approval", key, "denied", {"tool": tool_name, "source": "no_ui"})
            return False

        request_id = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[request_id] = fut
        try:
            await send({
                "request_id": request_id,
                "tool": tool_name,
                "key": key,
                "reason": reason,
                "args": {k: (str(v)[:200]) for k, v in args.items()},
                "timeout_s": timeout,
            })
            decision = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            decision = "deny"
        finally:
            self._pending.pop(request_id, None)

        if decision in ("always", "never"):
            self.remember(key, decision)
        allowed = decision in ("allow", "allow_once", "always")
        record_audit_event(
            "approval", key, "approved" if allowed else "denied",
            {"tool": tool_name, "decision": decision, "reason": reason},
        )
        return allowed


# Process-wide manager
approval_manager = ApprovalManager()

