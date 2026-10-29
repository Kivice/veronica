"""Tool schemas and dispatching for structured function calling."""
from __future__ import annotations

import logging
from typing import Any

from ..tools import (
    clipboard_tool,
    close_application,
    execute_command,
    execute_tool,
    get_network_status,
    get_system_telemetry,
    get_veronica_logs,
    iot_control,
    launch_application,
    media_control,
    memory_store,
    search_web,
    timer_reminder,
    window_manager,
    workspace_macro,
)

logger = logging.getLogger("veronica.intelligence.tools")

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_system_telemetry",
            "description": "Fetch real-time Windows hardware vitals including CPU per-core load, RAM usage, battery charging state, disk headroom, network I/O, and top memory-consuming processes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_status",
            "description": "Inspect real-time network telemetry including local IP address, hostname, active network interfaces, and total bytes transmitted/received.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "window_manager",
            "description": "Manage active Windows desktop windows: list visible windows, focus/bring-to-front a window by title, or minimize a window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "focus", "minimize"]},
                    "target": {"type": "string"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_tool",
            "description": "Read or write the Windows system clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get", "set"]},
                    "text": {"type": "string"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "timer_reminder",
            "description": "Manage tactical countdown timers and reminders on the desktop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["set", "list", "cancel"]},
                    "label": {"type": "string"},
                    "seconds": {"type": "integer"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_application",
            "description": "Launch a Windows application, executable, or web URL.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_application",
            "description": "Close or quit a running Windows application by name (e.g., 'spotify', 'chrome', 'notepad', 'vscode', 'calc').",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": "Control Windows system volume (exact 0-100% level or relative step) or active media playback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["volume_up", "volume_down", "set_volume", "mute", "play_pause", "play", "pause", "next", "prev", "stop"],
                    },
                    "level": {"type": "integer", "description": "Exact target volume percentage (0-100) when action is set_volume"},
                    "step": {"type": "integer", "description": "Volume step percentage (default 12) for volume_up / volume_down"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "iot_control",
            "description": "Control local IoT & Smart Home devices (Home Assistant, Shelly, WLED, LAN webhooks) with RFC1918 anti-SSRF and physical lock security gates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "scan", "register", "remove", "turn_on", "turn_off", "toggle", "lock", "unlock"],
                    },
                    "target": {"type": "string"},
                    "protocol": {"type": "string", "enum": ["home_assistant", "shelly", "wled", "webhook"]},
                    "endpoint": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "confirm_security": {"type": "boolean"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_veronica_logs",
            "description": "Retrieve recent Veronica operational logs and structured security/action audit events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "include_audit": {"type": "boolean"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_macro",
            "description": "Engage tactical workspace macros: 'dev', 'focus', or 'scan'.",
            "parameters": {
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["dev", "focus", "scan"]}},
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_store",
            "description": "Manage Veronica's SQLite + FTS5 persistent tactical memory bank.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["get", "set", "search", "delete", "list", "wipe"]},
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Perform web reconnaissance by opening a search query in the browser.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a PowerShell terminal command on Windows and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


def dispatch_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a structured tool call by routing to the appropriate underlying implementation."""
    logger.info("Dispatching tool call: %s", tool_name)
    try:
        if tool_name in ("get_system_telemetry", "system_status", "telemetry"):
            return get_system_telemetry()
        elif tool_name in ("get_network_status", "network_status"):
            return get_network_status()
        elif tool_name == "window_manager":
            return window_manager(str(arguments.get("action", "list")), str(arguments.get("target", "")))
        elif tool_name == "clipboard_tool":
            return clipboard_tool(str(arguments.get("action", "get")), str(arguments.get("text", "")))
        elif tool_name == "timer_reminder":
            return timer_reminder(
                str(arguments.get("action", "list")),
                str(arguments.get("label", "Timer")),
                int(arguments.get("seconds", 60)),
            )
        elif tool_name == "launch_application":
            app = arguments.get("app_name") or arguments.get("app", "")
            return launch_application(str(app))
        elif tool_name == "close_application":
            app = arguments.get("app_name") or arguments.get("app", "")
            return close_application(str(app), force=bool(arguments.get("force", False)))
        elif tool_name == "media_control":
            lvl = arguments.get("level")
            step = int(arguments.get("step", 12))
            return media_control(
                str(arguments.get("action", "play_pause")),
                level=int(lvl) if lvl is not None else None,
                step=step,
            )
        elif tool_name in ("iot_control", "iot"):
            return iot_control(
                action=str(arguments.get("action", "list")),
                target=str(arguments.get("target", "")),
                protocol=str(arguments.get("protocol", "home_assistant")),
                endpoint=str(arguments.get("endpoint", "")),
                entity_id=str(arguments.get("entity_id", "")),
                confirm_security=bool(arguments.get("confirm_security", False)),
            )
        elif tool_name in ("get_veronica_logs", "veronica_logs", "logs"):
            return get_veronica_logs(
                limit=int(arguments.get("limit", 25)),
                include_audit=bool(arguments.get("include_audit", True)),
            )
        elif tool_name == "workspace_macro":
            return workspace_macro(str(arguments.get("mode", "dev")))
        elif tool_name == "memory_store":
            return memory_store(
                str(arguments.get("action", "list")),
                arguments.get("key") or "",
                arguments.get("value"),
            )
        elif tool_name == "search_web":
            return search_web(str(arguments.get("query", "")))
        elif tool_name == "execute_command":
            return execute_command(str(arguments.get("command", "")))
        return execute_tool(tool_name, arguments)
    except Exception as exc:
        logger.error("Error executing tool %s: %s", tool_name, exc, exc_info=True)
        return {"status": "error", "message": str(exc)}
