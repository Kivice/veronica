"""Veronica Desktop Agent Tool Engine.
Provides real system telemetry, application launching, terminal command execution,
media control, window management, clipboard access, tactical timers, network recon,
screen capture, and SQLite + FTS5 persistent local memory.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import psutil

from .audit_logger import get_veronica_logs, record_audit_event, setup_veronica_logging
from .iot import iot_control
from .memory_db import TacticalMemoryBank

setup_veronica_logging()

CREATE_NO_WINDOW = 0x08000000

APP_SHORTCUTS = {
    "vscode": ["code"],
    "code": ["code"],
    "vs code": ["code"],
    "visual studio code": ["code"],
    "calc": ["calc.exe"],
    "calculator": ["calc.exe"],
    "notepad": ["notepad.exe"],
    "editor": ["notepad.exe"],
    "terminal": ["wt.exe", "powershell.exe"],
    "powershell": ["powershell.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "taskmgr": ["taskmgr.exe"],
    "task manager": ["taskmgr.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "browser": ["msedge.exe", "chrome.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "spotify": [
        f"{os.environ.get('APPDATA', '')}\\Spotify\\Spotify.exe",
        f"{os.environ.get('LOCALAPPDATA', '')}\\Microsoft\\WindowsApps\\Spotify.exe",
        "spotify:",
    ],
    "settings": ["ms-settings:"],
    "snipping tool": ["snippingtool.exe"],
    "paint": ["mspaint.exe"],
}

SITE_SHORTCUTS: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
    "wikipedia": "https://www.wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "hackernews": "https://news.ycombinator.com",
    "hacker news": "https://news.ycombinator.com",
    "amazon": "https://www.amazon.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "docs": "https://docs.google.com",
    "google docs": "https://docs.google.com",
    "calendar": "https://calendar.google.com",
    "google calendar": "https://calendar.google.com",
    "arxiv": "https://arxiv.org",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
}

DOMAIN_LIKE_RE = re.compile(
    r"^(?:https?://|www\.)?[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.(?:com|org|net|io|ai|dev|edu|gov|co|tv|me|gg|app)(?:/.*)?$",
    re.IGNORECASE,
)

MEMORY_DIR = Path.home() / ".veronica"
MEMORY_FILE = MEMORY_DIR / "memory.json"
CREDENTIALS_FILE = MEMORY_DIR / "credentials.json"

_memory_bank: TacticalMemoryBank | None = None
_active_timers: dict[str, dict[str, Any]] = {}
_timers_lock = threading.Lock()


def _get_memory_bank() -> TacticalMemoryBank:
    global _memory_bank
    if _memory_bank is None:
        _memory_bank = TacticalMemoryBank(json_path=MEMORY_FILE)
    return _memory_bank


def get_credentials() -> dict[str, str]:
    """Load persistent API credentials from ~/.veronica/credentials.json, services/voice/.env, and ~/.env."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    creds: dict[str, str] = {}
    if CREDENTIALS_FILE.exists():
        try:
            creds = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except Exception:
            creds = {}

    # Merge .env files (project services/voice/.env and ~/.env take precedence if updated via CLI)
    for env_path in (
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path.home() / ".env",
    ):
        try:
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip().upper()
                        v = v.strip().strip('"').strip("'")
                        if not v:
                            continue
                        if k == "GROQ_API_KEY":
                            creds["groq"] = v
                        elif k == "OPENAI_API_KEY":
                            creds["openai"] = v
                        elif k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                            creds["gemini"] = v
                        elif k == "ANTHROPIC_API_KEY":
                            creds["anthropic"] = v
                        elif k == "OLLAMA_URL":
                            creds["ollama"] = v
        except Exception:
            pass

    return creds


def save_credentials(creds: dict[str, str]) -> dict[str, str]:
    """Persist API credentials to ~/.veronica/credentials.json and services/voice/.env."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    existing = get_credentials()
    for k, v in creds.items():
        if isinstance(v, str):
            clean_v = v.strip()
            if clean_v:
                existing[k.lower()] = clean_v
    try:
        CREDENTIALS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Also persist to services/voice/.env
    try:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        lines = []
        if existing.get("groq"):
            lines.append(f"GROQ_API_KEY={existing['groq']}")
        if existing.get("openai"):
            lines.append(f"OPENAI_API_KEY={existing['openai']}")
        if existing.get("gemini"):
            lines.append(f"GEMINI_API_KEY={existing['gemini']}")
        if existing.get("anthropic"):
            lines.append(f"ANTHROPIC_API_KEY={existing['anthropic']}")
        if existing.get("ollama"):
            lines.append(f"OLLAMA_URL={existing['ollama']}")
        if lines:
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass

    return existing


def _ensure_memory_file() -> dict[str, Any]:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    bank = _get_memory_bank()
    notes = bank.list_all()
    doc = {
        "name": "Veronica",
        "role": "Tactical Desktop Assistant",
        "notes": notes,
        "preferences": {"voice": "en-US-AvaNeural", "theme": "ironman-tactical"},
    }
    if not MEMORY_FILE.exists():
        try:
            MEMORY_FILE.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        except Exception:
            pass
    return doc


def get_system_telemetry() -> dict[str, Any]:
    """Retrieve real-time hardware telemetry: CPU, RAM, battery, disk, network, and top processes."""
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

    # Network I/O snapshot
    net_io = psutil.net_io_counters()
    net_info = {
        "sent_mb": round(net_io.bytes_sent / (1024 * 1024), 1) if net_io else 0.0,
        "recv_mb": round(net_io.bytes_recv / (1024 * 1024), 1) if net_io else 0.0,
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
        "network": net_info,
        "top_processes": top_procs[:5],
    }


def get_network_status() -> dict[str, Any]:
    """Perform local network telemetry and connectivity diagnostics."""
    net_io = psutil.net_io_counters()
    local_ip = "127.0.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
    except Exception:
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass

    active_ifaces = []
    try:
        stats = psutil.net_if_stats()
        for iface, st in stats.items():
            if st.isup and "loopback" not in iface.lower():
                active_ifaces.append({"name": iface, "speed_mbps": st.speed})
    except Exception:
        pass

    return {
        "status": "success",
        "local_ip": local_ip,
        "hostname": socket.gethostname(),
        "bytes_sent_mb": round(net_io.bytes_sent / (1024 * 1024), 1) if net_io else 0.0,
        "bytes_recv_mb": round(net_io.bytes_recv / (1024 * 1024), 1) if net_io else 0.0,
        "interfaces": active_ifaces[:4],
    }


def window_manager(action: str = "list", target: str = "") -> dict[str, Any]:
    """List open desktop windows, focus a window by title, or minimize/restore windows via Win32."""
    clean_act = action.lower().strip()
    if sys.platform != "win32":
        return {"status": "error", "message": "Window management requires Windows."}

    user32 = ctypes.windll.user32
    windows: list[dict[str, Any]] = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _enum_cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title and title not in ("Program Manager", "Windows Input Experience", "Settings"):
                    windows.append({"hwnd": int(hwnd), "title": title})
        return True

    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)

    if clean_act == "list":
        return {
            "status": "success",
            "count": len(windows),
            "windows": [w["title"] for w in windows[:15]],
        }

    target_lower = target.lower().strip()
    if not target_lower:
        return {"status": "error", "message": "Target window title required."}

    matched = [w for w in windows if target_lower in w["title"].lower()]
    if not matched:
        return {"status": "error", "message": f"No active window matching '{target}'."}

    chosen = matched[0]
    hwnd = chosen["hwnd"]
    SW_RESTORE = 9
    SW_MINIMIZE = 6

    if clean_act in ("focus", "activate", "show"):
        user32.ShowWindow(hwnd, SW_RESTORE)
        # Windows blocks SetForegroundWindow from background processes; a synthetic ALT tap lifts the lock.
        VK_MENU = 0x12
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
        return {"status": "success", "action": "focus", "window": chosen["title"]}
    elif clean_act == "minimize":
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return {"status": "success", "action": "minimize", "window": chosen["title"]}

    return {"status": "error", "message": f"Unknown window action: '{action}'"}


def clipboard_tool(action: str = "get", text: str = "") -> dict[str, Any]:
    """Read or write the Windows system clipboard."""
    clean_act = action.lower().strip()
    if clean_act == "get":
        res = execute_command("Get-Clipboard -Raw")
        content = res.get("stdout", "")
        return {
            "status": "success",
            "action": "get",
            "content": content[:4000],
            "length": len(content),
        }
    elif clean_act in ("set", "copy", "write"):
        if not text:
            return {"status": "error", "message": "Text required to copy to clipboard."}
        safe = text.replace("'", "''")
        execute_command(f"Set-Clipboard -Value '{safe}'")
        return {
            "status": "success",
            "action": "set",
            "length": len(text),
            "message": "Copied text to Windows clipboard.",
        }
    return {"status": "error", "message": f"Unknown clipboard action: '{action}'"}


def timer_reminder(action: str = "list", label: str = "Timer", seconds: int = 60) -> dict[str, Any]:
    """Set, list, or cancel tactical countdown timers."""
    clean_act = action.lower().strip()
    now = time.time()

    with _timers_lock:
        # Prune expired
        expired = [k for k, v in _active_timers.items() if v["due_at"] <= now]
        for k in expired:
            _active_timers.pop(k, None)

        if clean_act == "list":
            items = [
                {
                    "label": k,
                    "remaining_seconds": max(0, round(v["due_at"] - now)),
                    "duration_seconds": v["duration"],
                }
                for k, v in _active_timers.items()
            ]
            return {"status": "success", "timers": items, "count": len(items)}

        elif clean_act in ("cancel", "clear", "delete"):
            if label and label in _active_timers:
                _active_timers.pop(label, None)
                return {"status": "success", "message": f"Cancelled timer '{label}'."}
            _active_timers.clear()
            return {"status": "success", "message": "All tactical timers cleared."}

        elif clean_act in ("set", "start", "add"):
            sec = max(1, min(int(seconds), 86400))
            clean_label = label.strip() or "Tactical Timer"
            due = now + sec
            _active_timers[clean_label] = {"due_at": due, "duration": sec}

            def _beep_when_done(lbl: str, wait_s: int):
                time.sleep(wait_s)
                with _timers_lock:
                    if lbl not in _active_timers:
                        return
                    _active_timers.pop(lbl, None)
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass

            t = threading.Thread(target=_beep_when_done, args=(clean_label, sec), daemon=True)
            t.start()
            return {
                "status": "success",
                "label": clean_label,
                "seconds": sec,
                "message": f"Timer '{clean_label}' armed for {sec} seconds.",
            }

    return {"status": "error", "message": f"Unknown timer action: '{action}'"}


def capture_screen_base64() -> str:
    """Capture the primary Windows display into a base64 JPEG string using native .NET System.Drawing."""
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
        "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
        "$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height); "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
        "$ms = New-Object System.IO.MemoryStream; "
        "$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Jpeg); "
        "$g.Dispose(); $bmp.Dispose(); "
        "[Convert]::ToBase64String($ms.ToArray())"
    )
    res = execute_command(ps_script)
    if res.get("status") == "success" and res.get("stdout"):
        return res["stdout"].strip()
    return ""


def _resolve_and_start(target: str) -> bool:
    """Start one launch candidate. Returns True only if Windows actually accepted it."""
    t = target.strip()
    if not t:
        return False
    # Absolute paths: must exist
    if os.path.isabs(t):
        if not os.path.exists(t):
            return False
        os.startfile(t)  # type: ignore[attr-defined]
        return True
    # Executables / scripts on PATH (e.g. code -> code.cmd)
    found = shutil.which(t)
    if found:
        if found.lower().endswith((".cmd", ".bat")):
            subprocess.Popen(["cmd", "/c", found], creationflags=CREATE_NO_WINDOW)
        else:
            subprocess.Popen([found], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        return True
    # ShellExecute resolves App Paths (chrome.exe, msedge.exe), URIs (spotify:, ms-settings:) etc.
    # It raises OSError if Windows cannot find the target, so failures are detected.
    os.startfile(t)  # type: ignore[attr-defined]
    return True


def launch_application(app_name: str) -> dict[str, Any]:
    """Launch a Windows application, user folder, or website URL."""
    clean = app_name.strip().lower()
    clean = re.sub(r"^(?:the|my)\s+", "", clean).strip()

    # 1. Known web platform shortcuts (e.g., "youtube", "github", "gmail", "reddit")
    if clean in SITE_SHORTCUTS:
        url = SITE_SHORTCUTS[clean]
        webbrowser.open(url)
        record_audit_event("browser", "open_site", "success", {"site": clean, "url": url})
        return {"status": "success", "app": app_name, "url": url, "message": f"Opened {app_name} ({url}) in browser."}

    # 2. Explicit URL or domain name (e.g., "youtube.com", "news.ycombinator.com", "https://...")
    if clean.startswith("http://") or clean.startswith("https://") or clean.startswith("www.") or DOMAIN_LIKE_RE.match(clean):
        url = clean if clean.startswith("http") else f"https://{clean}"
        webbrowser.open(url)
        record_audit_event("browser", "open_url", "success", {"url": url})
        return {"status": "success", "app": app_name, "url": url, "message": f"Opening {url} in default browser."}

    # 3. Common user folders ("downloads", "documents", "desktop", "pictures")
    folder_map = {
        "downloads": str(Path.home() / "Downloads"),
        "download": str(Path.home() / "Downloads"),
        "documents": str(Path.home() / "Documents"),
        "desktop": str(Path.home() / "Desktop"),
        "pictures": str(Path.home() / "Pictures"),
    }
    if clean in folder_map and os.path.exists(folder_map[clean]):
        os.startfile(folder_map[clean])  # type: ignore[attr-defined]
        record_audit_event("app", "open_folder", "success", {"folder": clean})
        return {"status": "success", "app": app_name, "message": f"Opened {clean.capitalize()} folder."}

    candidates = APP_SHORTCUTS.get(clean, [app_name, f"{app_name}.exe"])
    for cmd in candidates:
        try:
            if _resolve_and_start(cmd):
                record_audit_event("app", "launch", "success", {"app": app_name, "cmd": cmd})
                return {"status": "success", "app": app_name, "command": cmd, "message": f"Launched {app_name}."}
        except Exception:
            continue

    return {"status": "error", "app": app_name, "message": f"Unable to find an application called '{app_name}'"}


# Friendly name -> process image names
APP_PROCESS_MAP: dict[str, list[str]] = {
    "spotify": ["spotify.exe"],
    "vscode": ["code.exe"], "vs code": ["code.exe"], "code": ["code.exe"], "visual studio code": ["code.exe"],
    "chrome": ["chrome.exe"], "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"], "microsoft edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "notepad": ["notepad.exe"],
    "calc": ["calculatorapp.exe", "calculator.exe"], "calculator": ["calculatorapp.exe", "calculator.exe"],
    "taskmgr": ["taskmgr.exe"], "task manager": ["taskmgr.exe"],
    "terminal": ["windowsterminal.exe"], "windows terminal": ["windowsterminal.exe"],
    "settings": ["systemsettings.exe"],
    "paint": ["mspaint.exe"],
    "discord": ["discord.exe"],
    "steam": ["steam.exe", "steamwebhelper.exe"],
    "teams": ["ms-teams.exe", "teams.exe"],
    "outlook": ["outlook.exe", "olk.exe"],
    "word": ["winword.exe"], "excel": ["excel.exe"], "powerpoint": ["powerpnt.exe"],
    "slack": ["slack.exe"], "zoom": ["zoom.exe"], "whatsapp": ["whatsapp.exe"],
    "obs": ["obs64.exe"], "vlc": ["vlc.exe"],
}

# Never terminate these, no matter what the user (or an injected prompt) asks
PROTECTED_PROCESSES = frozenset({
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
    "sihost.exe", "ctfmon.exe", "searchhost.exe", "startmenuexperiencehost.exe", "memcompression",
    "conhost.exe", "runtimebroker.exe", "audiodg.exe", "spoolsv.exe", "msmpeng.exe",
})


def _visible_windows_for_pids(pids: set[int]) -> list[int]:
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    hwnds: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(hwnd, _l):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                hwnds.append(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return hwnds


def _self_and_ancestor_pids() -> set[int]:
    pids = {os.getpid()}
    try:
        p = psutil.Process(os.getpid())
        for parent in p.parents():
            pids.add(parent.pid)
    except Exception:
        pass
    return pids


def close_application(app_name: str, force: bool = False) -> dict[str, Any]:
    """Close a running application gracefully (WM_CLOSE), then terminate leftover background processes.

    If a window refuses to close (e.g. an unsaved-changes prompt) it is left alone unless force=True.
    """
    clean = app_name.strip().lower()
    clean = re.sub(r"^(?:the|my)\s+", "", clean)
    clean = re.sub(r"\s+(?:app|application|window|program)$", "", clean).strip()
    if not clean:
        return {"status": "error", "message": "Which application should I close?"}

    targets = set(APP_PROCESS_MAP.get(clean, []))
    stem = clean.replace(" ", "")
    guard = _self_and_ancestor_pids()

    matched: list[psutil.Process] = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pname = (p.info.get("name") or "").lower()
            if not pname or pname in PROTECTED_PROCESSES or p.info["pid"] in guard:
                continue
            pstem = pname[:-4] if pname.endswith(".exe") else pname
            if targets:
                hit = pname in targets
            else:
                hit = len(stem) >= 3 and (pstem == stem or pstem.startswith(stem))
            if not hit:
                continue
            # Never kill Veronica's own HUD / service processes (e.g. "close edge" while the HUD runs in Edge)
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if "\\veronica\\" in cmd or "veronica_voice" in cmd:
                continue
            matched.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not matched:
        return {"status": "error", "app": app_name, "message": f"{app_name} is not running."}

    pids = {p.pid for p in matched}
    # 1. Graceful: ask every top-level window to close
    WM_CLOSE = 0x0010
    hwnds = _visible_windows_for_pids(pids)
    if sys.platform == "win32":
        for h in hwnds:
            ctypes.windll.user32.PostMessageW(h, WM_CLOSE, 0, 0)

    gone, alive = psutil.wait_procs(matched, timeout=2.5)

    # 2. If no visible window is left (closed, or minimized to tray) kill lingering background processes
    remaining_windows = _visible_windows_for_pids({p.pid for p in alive})
    if alive and (force or not remaining_windows):
        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        gone2, alive = psutil.wait_procs(alive, timeout=2.0)

    if alive and remaining_windows:
        return {
            "status": "partial",
            "app": app_name,
            "message": f"{app_name} is waiting on a prompt (possibly unsaved changes). Say 'force close {app_name}' to terminate it.",
        }
    if alive:
        return {"status": "error", "app": app_name, "message": f"Access denied closing {app_name}."}
    return {"status": "success", "app": app_name, "closed_processes": len(matched), "message": f"Closed {app_name}."}


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


def _windows_master_volume(target_percent: float | None = None, delta_percent: float | None = None) -> int | None:
    """Read or set exact Windows Master Volume (0-100%) using CoreAudio IAudioEndpointVolume COM via ctypes."""
    if sys.platform != "win32":
        return None
    try:
        from ctypes import POINTER, Structure, byref, c_float, c_int, c_void_p, HRESULT
        from ctypes.wintypes import DWORD

        class _GUID(Structure):
            _fields_ = [
                ("Data1", DWORD),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

            def __init__(self, l, w1, w2, *b):
                super().__init__(l, w1, w2, (ctypes.c_ubyte * 8)(*b))

        CLSID_MMDeviceEnumerator = _GUID(0xBCDE0395, 0xE52F, 0x467C, 0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E)
        IID_IMMDeviceEnumerator = _GUID(0xA95664D2, 0x9614, 0x4F35, 0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6)
        IID_IAudioEndpointVolume = _GUID(0x5CDF2C82, 0x841E, 0x4546, 0x97, 0x22, 0x0C, 0xF7, 0x40, 0x78, 0x22, 0x9A)

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        enum_ptr = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(CLSID_MMDeviceEnumerator), None, 23, byref(IID_IMMDeviceEnumerator), byref(enum_ptr)
        )
        if hr != 0 or not enum_ptr.value:
            return None

        vtable = ctypes.cast(enum_ptr, POINTER(POINTER(c_void_p))).contents
        GetDefaultAudioEndpoint = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_int, c_int, POINTER(c_void_p))(vtable[4])
        dev_ptr = c_void_p()
        if GetDefaultAudioEndpoint(enum_ptr, 0, 1, byref(dev_ptr)) != 0 or not dev_ptr.value:
            return None

        dev_vt = ctypes.cast(dev_ptr, POINTER(POINTER(c_void_p))).contents
        Activate = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(_GUID), DWORD, c_void_p, POINTER(c_void_p))(dev_vt[3])
        vol_ptr = c_void_p()
        if Activate(dev_ptr, byref(IID_IAudioEndpointVolume), 23, None, byref(vol_ptr)) != 0 or not vol_ptr.value:
            return None

        vol_vt = ctypes.cast(vol_ptr, POINTER(POINTER(c_void_p))).contents
        GetVol = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_float))(vol_vt[9])
        SetVol = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_float, c_void_p)(vol_vt[7])
        SetMute = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_int, c_void_p)(vol_vt[14])

        cur = c_float()
        GetVol(vol_ptr, byref(cur))
        cur_pct = cur.value * 100.0

        if target_percent is not None:
            new_pct = max(0.0, min(100.0, float(target_percent)))
            if new_pct > 0:
                SetMute(vol_ptr, 0, None)
            SetVol(vol_ptr, c_float(new_pct / 100.0), None)
            return round(new_pct)
        if delta_percent is not None:
            new_pct = max(0.0, min(100.0, cur_pct + float(delta_percent)))
            if delta_percent > 0:
                SetMute(vol_ptr, 0, None)
            SetVol(vol_ptr, c_float(new_pct / 100.0), None)
            return round(new_pct)
        return round(cur_pct)
    except Exception:
        return None


def media_control(action: str, level: int | None = None, step: int = 12) -> dict[str, Any]:
    """Control Windows volume (CoreAudio + OSD key events) or media playback with zero latency."""
    vk_map = {
        "volume_up": 0xAF,
        "volume_down": 0xAE,
        "set_volume": 0xAF,
        "mute": 0xAD,
        "unmute": 0xAD,
        "play_pause": 0xB3,
        "play": 0xB3,
        "pause": 0xB3,
        "unpause": 0xB3,
        "stop": 0xB2,
        "next": 0xB0,
        "prev": 0xB1,
    }
    clean = action.lower().strip()
    if level is not None and clean in ("volume_up", "volume_down", "volume", "set_volume", ""):
        clean = "set_volume"

    if clean == "set_volume" and level is not None:
        new_vol = _windows_master_volume(target_percent=float(level))
        # Tap volume key once to trigger the Windows visual volume flyout
        try:
            ctypes.windll.user32.keybd_event(0xAF if level > 0 else 0xAE, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xAF if level > 0 else 0xAE, 0, 2, 0)
        except Exception:
            pass
        record_audit_event("media", "set_volume", "success", {"volume_percent": new_vol if new_vol is not None else level})
        return {
            "status": "success",
            "action": "set_volume",
            "volume_percent": new_vol if new_vol is not None else level,
            "mode": "coreaudio",
        }

    if clean == "volume_up":
        new_vol = _windows_master_volume(delta_percent=float(abs(step)))
        try:
            # If CoreAudio succeeded, 1 key tap shows OSD; otherwise send 6 key taps (+12%)
            taps = 1 if new_vol is not None else max(1, abs(step) // 2)
            for _ in range(taps):
                ctypes.windll.user32.keybd_event(0xAF, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAF, 0, 2, 0)
        except Exception:
            pass
        record_audit_event("media", "volume_up", "success", {"volume_percent": new_vol})
        return {"status": "success", "action": "volume_up", "volume_percent": new_vol, "mode": "coreaudio"}

    if clean == "volume_down":
        new_vol = _windows_master_volume(delta_percent=-float(abs(step)))
        try:
            taps = 1 if new_vol is not None else max(1, abs(step) // 2)
            for _ in range(taps):
                ctypes.windll.user32.keybd_event(0xAE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAE, 0, 2, 0)
        except Exception:
            pass
        record_audit_event("media", "volume_down", "success", {"volume_percent": new_vol})
        return {"status": "success", "action": "volume_down", "volume_percent": new_vol, "mode": "coreaudio"}

    vk = vk_map.get(clean)
    if not vk:
        return {"status": "error", "message": f"Unknown media action: {action}"}

    try:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        record_audit_event("media", clean, "success")
        return {"status": "success", "action": clean, "mode": "native"}
    except Exception:
        ps_script = f"""
        $wscript = New-Object -ComObject WScript.Shell;
        $wscript.SendKeys([char]{vk});
        """
        execute_command(ps_script)
        record_audit_event("media", clean, "fallback")
        return {"status": "success", "action": clean, "mode": "fallback"}


def memory_store(action: str, key: str = "", value: Any = None) -> dict[str, Any]:
    """Store, retrieve, FTS5-search, export, or wipe persistent tactical memory."""
    bank = _get_memory_bank()
    clean_act = action.lower().strip()

    if clean_act == "get":
        notes = bank.list_all()
        if not key:
            mem = _ensure_memory_file()
            return {"status": "success", "memory": mem, "notes": notes}
        val = bank.get(key)
        return {"status": "success", "key": key, "value": val, "notes": notes}

    elif clean_act == "set":
        if not key:
            return {"status": "error", "message": "Key required for store", "notes": bank.list_all()}
        notes = bank.set(key, value)
        return {
            "status": "success",
            "message": f"Remembered '{key}'",
            "key": key,
            "value": value,
            "notes": notes,
        }

    elif clean_act == "search":
        matches = bank.search(key or str(value or ""))
        return {"status": "success", "query": key, "matches": matches, "notes": bank.list_all()}

    elif clean_act == "delete":
        notes = bank.delete(key)
        return {"status": "success", "message": f"Cleared memory for '{key}'", "notes": notes}

    elif clean_act in ("wipe", "clear_all"):
        bank.wipe()
        return {"status": "success", "message": "All tactical memory banks securely wiped and vacuumed.", "notes": {}}

    elif clean_act in ("list", "export"):
        notes = bank.list_all()
        return {"status": "success", "notes": notes}

    return {"status": "error", "message": f"Unknown memory action '{action}'", "notes": bank.list_all()}


def _fetch_live_web_snippets(query: str, max_results: int = 4) -> list[dict[str, str]]:
    """Perform live HTTP web retrieval (DuckDuckGo Lite/HTML + Wikipedia summary) so Veronica can read web results."""
    snippets: list[dict[str, str]] = []
    try:
        import html as html_mod
        import httpx

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        with httpx.Client(timeout=4.5, follow_redirects=True, headers=headers) as client:
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp = client.get(ddg_url)
            if resp.status_code == 200:
                blocks = re.findall(
                    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                    resp.text,
                    re.DOTALL,
                )
                for href, raw_title, raw_snip in blocks[:max_results]:
                    title = html_mod.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
                    snip = html_mod.unescape(re.sub(r"<[^>]+>", "", raw_snip)).strip()
                    if title or snip:
                        snippets.append({"title": title, "snippet": snip, "url": href})
    except Exception:
        pass
    return snippets


def browser_agent(
    action: str = "search",
    query: str = "",
    site: str = "",
    url: str = "",
    read_content: bool = False,
) -> dict[str, Any]:
    """Agentic Web Browser Controller:
      - 'open_site' / 'navigate': Open a known site shortcut ('youtube', 'github', 'gmail', 'reddit', etc.) or URL.
      - 'search': Search on Google, YouTube, GitHub, Reddit, Wikipedia, StackOverflow, or Maps, and optionally fetch live snippets.
      - 'play_youtube': Find the top matching YouTube video for `query` and open/play it directly in the browser.
      - 'research' / 'read_page': Fetch live search results or extract readable text from a URL for agentic reasoning.
      - 'tab_control': Send active browser tab shortcuts ('new_tab', 'close_tab', 'reopen_tab', 'next_tab', 'prev_tab', 'refresh', 'back', 'forward').
    """
    act = action.lower().strip()
    clean_q = (query or url).strip()
    clean_site = site.lower().strip()

    # 1. Tab & Browser Window Keyboard Control
    tab_keys = {
        "new_tab": "^t",
        "close_tab": "^w",
        "reopen_tab": "^+t",
        "next_tab": "^{TAB}",
        "prev_tab": "^+{TAB}",
        "refresh": "^r",
        "reload": "^r",
        "back": "%{LEFT}",
        "forward": "%{RIGHT}",
        "address_bar": "^l",
        "fullscreen": "{F11}",
    }
    if act in tab_keys or (act == "tab_control" and clean_q.lower().replace(" ", "_") in tab_keys):
        key_cmd = tab_keys.get(act) or tab_keys[clean_q.lower().replace(" ", "_")]
        # Focus browser first
        for b_title in ("Edge", "Chrome", "Firefox", "Brave"):
            f_res = window_manager("focus", b_title)
            if f_res.get("status") == "success":
                break
        time.sleep(0.1)
        execute_command(f"$ws = New-Object -ComObject WScript.Shell; $ws.SendKeys('{key_cmd}')")
        record_audit_event("browser", f"tab_{act}", "success", {"key": key_cmd})
        return {"status": "success", "action": act, "message": f"Executed browser control '{act}'."}

    # 2. Direct YouTube Video Auto-Play
    if act == "play_youtube" or (clean_site in ("youtube", "yt") and act in ("play", "watch")):
        yt_search_url = f"https://www.youtube.com/results?search_query={quote_plus(clean_q)}"
        watch_url = yt_search_url
        try:
            import httpx
            with httpx.Client(timeout=4.0, follow_redirects=True) as client:
                r = client.get(yt_search_url, headers={"User-Agent": "Mozilla/5.0"})
                m = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
                if m:
                    watch_url = f"https://www.youtube.com/watch?v={m.group(1)}"
        except Exception:
            pass
        webbrowser.open(watch_url)
        record_audit_event("browser", "play_youtube", "success", {"query": clean_q, "url": watch_url})
        return {
            "status": "success",
            "action": "play_youtube",
            "query": clean_q,
            "url": watch_url,
            "message": f"Playing '{clean_q}' on YouTube ({watch_url}).",
        }

    # 3. Direct URL / Site Navigation
    if act in ("open_site", "navigate", "open_url", "open"):
        target = clean_site or clean_q.lower()
        target = re.sub(r"^(?:https?://)?(?:www\.)?", "", target).rstrip("/")
        if target in SITE_SHORTCUTS:
            dest = SITE_SHORTCUTS[target]
        elif clean_q.lower() in SITE_SHORTCUTS:
            dest = SITE_SHORTCUTS[clean_q.lower()]
        elif clean_q.startswith(("http://", "https://")):
            dest = clean_q
        elif "." in clean_q and " " not in clean_q:
            dest = f"https://{clean_q}"
        else:
            dest = f"https://www.google.com/search?q={quote_plus(clean_q)}"
        webbrowser.open(dest)
        record_audit_event("browser", "navigate", "success", {"url": dest})
        return {"status": "success", "action": "navigate", "url": dest, "message": f"Opened {dest} in browser."}

    # 4. Read Webpage Content Directly
    if act in ("read_page", "read_url") and clean_q:
        target_url = clean_q if clean_q.startswith("http") else f"https://{clean_q}"
        try:
            import html as html_mod
            import httpx
            with httpx.Client(timeout=5.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = client.get(target_url)
                raw = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", resp.text, flags=re.DOTALL | re.IGNORECASE)
                text = html_mod.unescape(re.sub(r"<[^>]+>", " ", raw))
                text = re.sub(r"\s+", " ", text).strip()[:2500]
                return {"status": "success", "action": "read_page", "url": target_url, "content": text}
        except Exception as exc:
            return {"status": "error", "url": target_url, "message": f"Could not read page: {exc}"}

    # 5. Live Research / Site-Specific Search
    site_search_templates = {
        "youtube": "https://www.youtube.com/results?search_query={q}",
        "yt": "https://www.youtube.com/results?search_query={q}",
        "github": "https://github.com/search?q={q}",
        "reddit": "https://www.reddit.com/search/?q={q}",
        "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
        "stackoverflow": "https://stackoverflow.com/search?q={q}",
        "amazon": "https://www.amazon.com/s?k={q}",
        "maps": "https://www.google.com/maps/search/{q}",
        "google": "https://www.google.com/search?q={q}",
    }
    encoded = quote_plus(clean_q)
    search_url = site_search_templates.get(clean_site, "https://www.google.com/search?q={q}").format(q=encoded)

    if act != "research":
        webbrowser.open(search_url)

    snippets = _fetch_live_web_snippets(clean_q) if (read_content or act == "research") else []
    record_audit_event("browser", act, "success", {"query": clean_q, "site": clean_site or "google", "url": search_url})
    return {
        "status": "success",
        "action": act,
        "query": clean_q,
        "site": clean_site or "google",
        "url": search_url,
        "results": snippets,
        "message": f"Searched {clean_site or 'web'} for '{clean_q}'" + (f" ({len(snippets)} live snippets retrieved)" if snippets else ""),
    }


def search_web(query: str, site: str = "", read_content: bool = False) -> dict[str, Any]:
    """Open search query in default web browser (or site-specific search) and optionally fetch live snippets."""
    clean = query.strip()
    if clean.lower() in SITE_SHORTCUTS:
        return browser_agent("open_site", query=clean, site=clean.lower())
    if DOMAIN_LIKE_RE.match(clean):
        return browser_agent("open_site", url=clean)
    return browser_agent("search", query=clean, site=site, read_content=read_content)


def app_interact(
    app: str,
    action: str = "interact",
    content: str = "",
    target: str = "",
) -> dict[str, Any]:
    """Agentic Core Application Controller:
      - app='notepad': Create/write notes and open them in Notepad, or type text into active Notepad.
      - app='spotify': Search or play a specific song, artist, or playlist in Spotify ('spotify:search:...').
      - app='vscode': Open a folder, file, or create a snippet and open it in VS Code.
      - app='explorer': Open user folders ('downloads', 'documents', 'desktop') or search local files.
      - action='type' / 'hotkey': Focus any application window and send text or keyboard shortcuts.
    """
    clean_app = app.lower().strip()
    clean_act = action.lower().strip()

    # 1. Notepad Deep Interaction (Write note & open live in Notepad)
    if clean_app in ("notepad", "editor", "note", "notes"):
        notes_dir = Path.home() / "Documents" / "Veronica_Notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        fname = re.sub(r"[^a-zA-Z0-9_\-]", "_", target.strip()) if target.strip() else f"veronica_note_{int(time.time())}"
        if not fname.endswith((".txt", ".md")):
            fname += ".txt"
        fpath = notes_dir / fname
        text_body = content or target or "Veronica Tactical Note"
        fpath.write_text(text_body, encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(fpath)], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        record_audit_event("app_interact", "notepad_write", "success", {"file": str(fpath)})
        return {
            "status": "success",
            "app": "Notepad",
            "action": "write_note",
            "file": str(fpath),
            "message": f"Created '{fname}' and opened it in Notepad.",
        }

    # 2. Spotify Deep Interaction (Play / Search specific song or artist)
    if clean_app == "spotify":
        song_query = (content or target).strip()
        if not song_query:
            launch_application("spotify")
            time.sleep(0.3)
            media_control("play_pause")
            return {"status": "success", "app": "Spotify", "action": "play", "message": "Launched Spotify and started playback."}
        try:
            os.startfile(f"spotify:search:{quote_plus(song_query)}")  # type: ignore[attr-defined]
            time.sleep(0.8)
            media_control("play")
            record_audit_event("app_interact", "spotify_search", "success", {"query": song_query})
            return {
                "status": "success",
                "app": "Spotify",
                "action": "search_and_play",
                "query": song_query,
                "message": f"Opened '{song_query}' in Spotify.",
            }
        except Exception:
            # Fallback to web player search
            return browser_agent("search", query=f"site:open.spotify.com {song_query}")

    # 3. VS Code Deep Interaction (Open project/folder/file)
    if clean_app in ("vscode", "vs code", "code"):
        target_path = (target or content).strip() or "c:\\Users\\USER\\veronica"
        if target_path.lower() in ("veronica", "project", "workspace", "current"):
            target_path = "c:\\Users\\USER\\veronica"
        found_code = shutil.which("code")
        if found_code:
            subprocess.Popen(["cmd", "/c", found_code, target_path], creationflags=CREATE_NO_WINDOW)
            record_audit_event("app_interact", "vscode_open", "success", {"path": target_path})
            return {"status": "success", "app": "VS Code", "path": target_path, "message": f"Opened '{target_path}' in VS Code."}
        return launch_application("vscode")

    # 4. File Explorer & Local File Search
    if clean_app in ("explorer", "files", "file explorer", "folder"):
        q = (target or content).strip()
        if clean_act == "search_files" and q:
            matches: list[str] = []
            for root_dir in (Path.home() / "Downloads", Path.home() / "Documents", Path.home() / "Desktop"):
                if not root_dir.exists():
                    continue
                for p in root_dir.rglob(f"*{q}*"):
                    matches.append(str(p))
                    if len(matches) >= 15:
                        break
                if len(matches) >= 15:
                    break
            return {
                "status": "success",
                "app": "File Explorer",
                "action": "search_files",
                "query": q,
                "matches": matches,
                "count": len(matches),
                "message": f"Found {len(matches)} local files matching '{q}'.",
            }
        return launch_application(q or "explorer")

    # 5. Universal Window Focus + Type Text / Send Hotkey
    if clean_act in ("type", "hotkey", "send_keys") and content:
        if clean_app:
            window_manager("focus", clean_app)
            time.sleep(0.15)
        if clean_act == "type":
            clipboard_tool("set", content)
            execute_command("$ws = New-Object -ComObject WScript.Shell; $ws.SendKeys('^v')")
            msg = f"Typed text into {clean_app or 'active window'}."
        else:
            safe_keys = content.replace("'", "")
            execute_command(f"$ws = New-Object -ComObject WScript.Shell; $ws.SendKeys('{safe_keys}')")
            msg = f"Sent shortcut '{content}' to {clean_app or 'active window'}."
        record_audit_event("app_interact", clean_act, "success", {"app": clean_app})
        return {"status": "success", "app": clean_app, "action": clean_act, "message": msg}

    return launch_application(clean_app)


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
        net = get_network_status()
        return {
            "status": "success",
            "workspace": "scan",
            "telemetry": telem,
            "network": net,
            "message": f"Deep scan complete. CPU at {telem['cpu_percent']}%, RAM utilized: {telem['ram_percent']}%, IP: {net['local_ip']}.",
        }
    return {"status": "error", "message": f"Unknown workspace macro: '{name}'"}


def execute_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Universal dispatcher for Veronica tools."""
    name = tool_name.lower().strip()
    if name in ("system_status", "telemetry", "vitals"):
        return get_system_telemetry()
    elif name in ("network", "network_status", "net_status"):
        return get_network_status()
    elif name in ("window", "windows", "window_manager"):
        action = params.get("action", "list")
        target = params.get("target") or params.get("window", "")
        return window_manager(str(action), str(target))
    elif name in ("clipboard", "clipboard_tool"):
        action = params.get("action", "get")
        text = params.get("text", "")
        return clipboard_tool(str(action), str(text))
    elif name in ("timer", "timers", "timer_reminder", "reminder"):
        action = params.get("action", "list")
        label = params.get("label", "Timer")
        seconds = int(params.get("seconds", 60))
        return timer_reminder(str(action), str(label), seconds)
    elif name in ("workspace", "macro", "workspace_macro"):
        macro_name = params.get("name") or params.get("macro") or params.get("workspace", "dev")
        return workspace_macro(str(macro_name))
    elif name in ("launch_app", "launch", "open_app"):
        app = params.get("app") or params.get("target") or params.get("name", "")
        return launch_application(str(app))
    elif name in ("close_app", "close", "close_application", "kill_app", "quit_app"):
        app = params.get("app") or params.get("target") or params.get("name", "")
        return close_application(str(app), force=bool(params.get("force", False)))
    elif name in ("run_command", "command", "cmd", "exec"):
        cmd = params.get("command") or params.get("cmd", "")
        return execute_command(str(cmd))
    elif name in ("media_control", "media", "volume"):
        action = params.get("action", "")
        lvl = params.get("level")
        step = int(params.get("step", 12))
        return media_control(str(action), level=int(lvl) if lvl is not None else None, step=step)
    elif name in ("iot", "iot_control", "smart_home"):
        return iot_control(
            action=str(params.get("action", "list")),
            device=str(params.get("device", "")),
            state=str(params.get("state", "")),
            host=str(params.get("host", "")),
            device_type=str(params.get("device_type", "webhook")),
            confirm=bool(params.get("confirm", False)),
        )
    elif name in ("logs", "veronica_logs", "audit_logs", "get_veronica_logs"):
        return get_veronica_logs(int(params.get("lines", 25)))
    elif name in ("memory", "memory_store", "note"):
        action = params.get("action", "list")
        key = params.get("key", "")
        val = params.get("value")
        return memory_store(action, key, val)
    elif name in ("search_web", "search", "browse"):
        q = params.get("query") or params.get("q", "")
        return search_web(str(q), site=str(params.get("site", "")), read_content=bool(params.get("read_content", False)))
    elif name in ("browser_agent", "browser", "web_browser"):
        return browser_agent(
            action=str(params.get("action", "search")),
            query=str(params.get("query") or params.get("q", "")),
            site=str(params.get("site", "")),
            url=str(params.get("url", "")),
            read_content=bool(params.get("read_content", False)),
        )
    elif name in ("app_interact", "interact_app", "core_app"):
        return app_interact(
            app=str(params.get("app", "")),
            action=str(params.get("action", "interact")),
            content=str(params.get("content", "")),
            target=str(params.get("target", "")),
        )
    return {"status": "error", "message": f"Unknown tool: '{tool_name}'"}
