"""Veronica Desktop Agent Tool Engine.
Provides real system telemetry, application launching, terminal command execution,
media control, and persistent local memory.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

import psutil

APP_SHORTCUTS = {
    "vscode": ["code"],
    "code": ["code"],
    "calc": ["calc.exe"],
    "calculator": ["calc.exe"],
    "notepad": ["notepad.exe"],
    "terminal": ["wt.exe", "powershell.exe"],
    "powershell": ["powershell.exe"],
    "taskmgr": ["taskmgr.exe"],
    "task manager": ["taskmgr.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "spotify": ["spotify.exe"],
}

MEMORY_DIR = Path.home() / ".veronica"
MEMORY_FILE = MEMORY_DIR / "memory.json"


def _ensure_memory_file() -> dict[str, Any]:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        initial = {
            "name": "Veronica",
            "role": "Tactical Desktop Assistant",
            "notes": {},
            "preferences": {"voice": "en-US-AvaNeural", "theme": "ironman-tactical"},
        }
        MEMORY_FILE.write_text(json.dumps(initial, indent=2), encoding="utf-8")
        return initial
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_system_telemetry() -> dict[str, Any]:
    """Retrieve real-time hardware telemetry: CPU, RAM, battery, disk, and top processes."""
    mem = psutil.virtual_memory()
    cpu_overall = psutil.cpu_percent(interval=0.1)
    cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
    disk = psutil.disk_usage("C:\\")

    battery = psutil.sensors_battery()
    batt_info = {
        "percent": battery.percent if battery else 100,
        "is_charging": battery.power_plugged if battery else True,
        "has_battery": battery is not None,
    }

    # Top 5 memory-consuming processes
    top_procs = []
    for p in sorted(
        psutil.process_iter(["pid", "name", "memory_info"]),
        key=lambda x: (x.info.get("memory_info").rss if x.info.get("memory_info") else 0),
        reverse=True,
    )[:6]:
        try:
            info = p.info
            name = info.get("name") or "unknown"
            if name.lower() in ("system idle process", "system"):
                continue
            rss = info.get("memory_info").rss if info.get("memory_info") else 0
            top_procs.append({
                "pid": info.get("pid"),
                "name": name,
                "memory_mb": round(rss / (1024 * 1024), 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {
        "cpu_percent": cpu_overall,
        "cpu_cores": cpu_cores,
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_free_gb": round(mem.available / (1024**3), 1),
        "ram_percent": mem.percent,
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "battery": batt_info,
        "top_processes": top_procs[:5],
    }


def launch_application(app_name: str) -> dict[str, Any]:
    """Launch a Windows application or URL."""
    clean = app_name.strip().lower()
    
    # URL check
    if clean.startswith("http://") or clean.startswith("https://") or clean.startswith("www."):
        url = clean if clean.startswith("http") else f"https://{clean}"
        webbrowser.open(url)
        return {"status": "success", "message": f"Opening {url} in default browser."}

    candidates = APP_SHORTCUTS.get(clean, [app_name])
    for cmd in candidates:
        try:
            subprocess.Popen(
                cmd,
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            return {"status": "success", "app": app_name, "command": cmd, "message": f"Launched {app_name}."}
        except Exception as e:
            continue
            
    return {"status": "error", "message": f"Unable to launch application: '{app_name}'"}


def execute_command(command: str) -> dict[str, Any]:
    """Execute a safe shell command and return stdout/stderr."""
    clean = command.strip()
    if not clean:
        return {"status": "error", "message": "Empty command"}
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", clean],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timed out after 15 seconds."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def media_control(action: str) -> dict[str, Any]:
    """Control Windows volume or media playback."""
    # Virtual key codes on Windows:
    # 0xAF = Volume Up, 0xAE = Volume Down, 0xAD = Volume Mute, 0xB3 = Play/Pause
    vk_map = {
        "volume_up": 0xAF,
        "volume_down": 0xAE,
        "mute": 0xAD,
        "play_pause": 0xB3,
        "next": 0xB0,
        "prev": 0xB1,
    }
    vk = vk_map.get(action.lower())
    if not vk:
        return {"status": "error", "message": f"Unknown media action: {action}"}

    ps_script = f"""
    $wscript = New-Object -ComObject WScript.Shell;
    $wscript.SendKeys([char]{vk});
    """
    execute_command(ps_script)
    return {"status": "success", "action": action}


def memory_store(action: str, key: str = "", value: Any = None) -> dict[str, Any]:
    """Store, retrieve or list persistent memory."""
    mem = _ensure_memory_file()
    if action == "get":
        if not key:
            return {"status": "success", "memory": mem}
        return {"status": "success", "key": key, "value": mem.get("notes", {}).get(key)}
    elif action == "set":
        if not key:
            return {"status": "error", "message": "Key required for store"}
        notes = mem.setdefault("notes", {})
        notes[key] = value
        MEMORY_FILE.write_text(json.dumps(mem, indent=2), encoding="utf-8")
        return {"status": "success", "message": f"Remembered '{key}'", "key": key, "value": value}
    elif action == "delete":
        notes = mem.get("notes", {})
        if key in notes:
            del notes[key]
            MEMORY_FILE.write_text(json.dumps(mem, indent=2), encoding="utf-8")
        return {"status": "success", "message": f"Cleared memory for '{key}'"}
    elif action == "list":
        return {"status": "success", "notes": mem.get("notes", {})}
    return {"status": "error", "message": f"Unknown memory action '{action}'"}


def search_web(query: str) -> dict[str, Any]:
    """Open search query in default web browser."""
    clean = query.strip()
    url = f"https://www.google.com/search?q={clean}"
    webbrowser.open(url)
    return {"status": "success", "query": clean, "url": url, "message": f"Opened search for: '{clean}'"}


def workspace_macro(name: str) -> dict[str, Any]:
    """Execute tactical multi-step workspace routines."""
    clean = name.lower().strip()
    if clean in ("dev", "dev_mode", "developer"):
        repo_root = "c:\\Users\\USER\\veronica"
        launch_application("code")
        launch_application("powershell")
        git_res = execute_command(f"git -C {repo_root} status --short")
        branch_res = execute_command(f"git -C {repo_root} branch --show-current")
        branch = branch_res.get("stdout", "master")
        return {
            "status": "success",
            "workspace": "dev",
            "branch": branch,
            "git_status": git_res.get("stdout", "clean"),
            "message": f"Dev workspace deployed. VS Code and terminal active on branch '{branch}'.",
        }
    elif clean in ("focus", "focus_mode"):
        media_control("mute")
        return {
            "status": "success",
            "workspace": "focus",
            "message": "Focus protocol active. Audio muted and distractions suppressed.",
        }
    elif clean in ("scan", "diagnostic", "deep_scan"):
        telem = get_system_telemetry()
        return {
            "status": "success",
            "workspace": "scan",
            "telemetry": telem,
            "message": f"Deep scan complete. CPU at {telem['cpu_percent']}%, RAM utilized: {telem['ram_percent']}%.",
        }
    return {"status": "error", "message": f"Unknown workspace macro: '{name}'"}


def execute_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Universal dispatcher for Veronica tools."""
    name = tool_name.lower().strip()
    if name in ("system_status", "telemetry", "vitals"):
        return get_system_telemetry()
    elif name in ("workspace", "macro", "workspace_macro"):
        macro_name = params.get("name") or params.get("macro") or params.get("workspace", "dev")
        return workspace_macro(str(macro_name))
    elif name in ("launch_app", "launch", "open_app"):
        app = params.get("app") or params.get("target") or params.get("name", "")
        return launch_application(str(app))
    elif name in ("run_command", "command", "cmd", "exec"):
        cmd = params.get("command") or params.get("cmd", "")
        return execute_command(str(cmd))
    elif name in ("media_control", "media", "volume"):
        action = params.get("action", "")
        return media_control(str(action))
    elif name in ("memory", "memory_store", "note"):
        action = params.get("action", "list")
        key = params.get("key", "")
        val = params.get("value")
        return memory_store(action, key, val)
    elif name in ("search_web", "search", "browse"):
        q = params.get("query") or params.get("q", "")
        return search_web(str(q))
    return {"status": "error", "message": f"Unknown tool: '{tool_name}'"}
