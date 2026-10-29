"""Intent classification and fast-path directive router for Project Veronica."""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any, Callable, Optional

import psutil

from ..tools import (
    clipboard_tool,
    close_application,
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
from .models import IntentAnalysis, IntentType

logger = logging.getLogger("veronica.intelligence.intent")

APP_KEYWORDS_MAP: dict[str, list[str]] = {
    "spotify": ["spotify", "music app"],
    "vscode": ["vscode", "vs code", "visual studio code", "code editor"],
    "terminal": ["terminal", "powershell", "command prompt", "cmd", "wt.exe"],
    "calc": ["calculator", "calc"],
    "notepad": ["notepad", "text editor"],
    "taskmgr": ["task manager", "taskmgr", "task monitor", "activity monitor"],
    "chrome": ["google chrome", "chrome"],
    "edge": ["microsoft edge", "edge browser", "edge"],
    "firefox": ["firefox"],
    "explorer": ["file explorer", "files explorer", "explorer", "files"],
    "settings": ["windows settings", "system settings", "settings"],
    "paint": ["mspaint", "paint"],
    "discord": ["discord"],
    "steam": ["steam"],
    "slack": ["slack"],
    "teams": ["teams", "microsoft teams"],
    "zoom": ["zoom"],
    "vlc": ["vlc"],
    "obs": ["obs"],
}

DISPLAY_NAMES: dict[str, str] = {
    "vscode": "VS Code",
    "taskmgr": "Task Manager",
    "calc": "Calculator",
}

CLOSE_VERB_RE = re.compile(
    r"\b(?:force\s+close|force\s+quit|force\s+kill|close|quit|exit|kill|terminate|shut\s*down|stop\s+app)\b",
    re.IGNORECASE,
)
LAUNCH_VERB_RE = re.compile(
    r"\b(?:open|launch|start|run|pull\s+up|fire\s+up|deploy)\b",
    re.IGNORECASE,
)

NON_APP_TARGETS = frozenset({
    "system", "telemetry", "vitals", "dev", "focus", "scan", "music", "audio", "sound", "track", "song",
    "playback", "windows", "window", "timer", "timers", "clipboard", "network", "memory", "memories",
    "it", "that", "this", "up", "down", "all", "everything", "veronica", "volume", "log", "logs",
    "audit", "iot", "light", "lights", "lamp", "plug", "switch", "door", "lock", "garage",
})

VOLUME_SET_RE = re.compile(
    r"\b(?:set\s+(?:the\s+)?(?:volume|audio|sound)\s+(?:to|at)\s*(\d{1,3})\s*%?|"
    r"(?:volume|audio|sound)\s+(?:to|at|=)\s*(\d{1,3})\s*%?|"
    r"(?:volume|audio|sound)\s+(\d{1,3})\s*%)\b",
    re.IGNORECASE,
)
VOLUME_STEP_UP_RE = re.compile(
    r"\b(?:(?:increase|raise|turn\s+up|boost)\s+(?:the\s+)?(?:volume|sound|audio)\s+by\s+(\d{1,3})\s*%?|"
    r"(?:volume|sound|audio)\s+(?:up|increase)\s+(?:by\s+)?(\d{1,3})\s*%?)\b",
    re.IGNORECASE,
)
VOLUME_STEP_DOWN_RE = re.compile(
    r"\b(?:(?:decrease|lower|reduce|turn\s+down)\s+(?:the\s+)?(?:volume|sound|audio)\s+by\s+(\d{1,3})\s*%?|"
    r"(?:volume|sound|audio)\s+(?:down|decrease|lower)\s+(?:by\s+)?(\d{1,3})\s*%?)\b",
    re.IGNORECASE,
)
VOLUME_UP_RE = re.compile(
    r"\b(?:"
    r"(?:volume|sound|audio)\s+(?:up|increase|higher|louder|boost|raise)|"
    r"(?:increase|raise|boost|amplify|crank\s+up|turn\s+up)\s+(?:the\s+|my\s+)?(?:volume|sound|audio)|"
    r"turn\s+(?:the\s+|my\s+|it\s+)?(?:volume\s+|sound\s+|audio\s+)?up|"
    r"make\s+it\s+louder|louder"
    r")\b",
    re.IGNORECASE,
)
VOLUME_DOWN_RE = re.compile(
    r"\b(?:"
    r"(?:volume|sound|audio)\s+(?:down|decrease|lower|quieter|softer|reduce)|"
    r"(?:decrease|lower|reduce|drop|turn\s+down)\s+(?:the\s+|my\s+)?(?:volume|sound|audio)|"
    r"turn\s+(?:the\s+|my\s+|it\s+)?(?:volume\s+|sound\s+|audio\s+)?down|"
    r"make\s+it\s+(?:quieter|softer)|quieter|softer"
    r")\b",
    re.IGNORECASE,
)


def _friendly_app_name(app: str) -> str:
    return DISPLAY_NAMES.get(app.lower(), app.capitalize())


class IntentRouter:
    """Classifies user input into intent categories and executes zero-latency fast-path directives."""

    def classify(self, text: str) -> IntentAnalysis:
        clean = text.strip()
        lower = clean.lower()

        # 1. Memory Store Intent
        store_match = re.search(
            r"^(?:please\s+)?(?:remember\s+that|remember|save\s+memory|store\s+memory)\s+(?:that\s+)?(?:my\s+)?([a-zA-Z0-9_\-\s]{2,30}?)\s+(?:is|=|as|:)\s+(.+)$",
            clean,
            re.IGNORECASE,
        )
        if store_match:
            raw_key = store_match.group(1).strip()
            val = store_match.group(2).strip()
            key = re.sub(r"^(?:that|my)\s+", "", raw_key, flags=re.IGNORECASE).strip()
            return IntentAnalysis(
                intent=IntentType.MEMORY_STORE,
                confidence=0.98,
                raw_query=clean,
                params={"key": key, "value": val},
            )

        # 2. Memory Query Intent
        search_mem_match = re.search(
            r"^(?:search\s+memory\s+for|find\s+in\s+memory|recall)\s+(.+?)\??$",
            lower,
        )
        if search_mem_match:
            q = search_mem_match.group(1).strip()
            return IntentAnalysis(
                intent=IntentType.MEMORY_QUERY,
                confidence=0.96,
                raw_query=clean,
                params={"key": q},
            )

        query_match = re.search(
            r"^(?:what\s+is\s+my|do\s+you\s+remember\s+(?:my\s+)?|what\s+do\s+you\s+remember\s+about\s+(?:my\s+)?)\s*([a-zA-Z0-9_\-\s]{2,30}?)\??$",
            lower,
        )
        if query_match:
            raw_key = query_match.group(1).strip()
            key = re.sub(r"^(?:that|my)\s+", "", raw_key).strip()
            if key not in ("ip", "ip address", "local ip", "cpu", "ram", "battery", "clipboard"):
                return IntentAnalysis(
                    intent=IntentType.MEMORY_QUERY,
                    confidence=0.95,
                    raw_query=clean,
                    params={"key": key},
                )

        # 3. Memory List Intent
        if any(w in lower for w in ("what do you remember", "list memories", "show memories", "what is in your memory", "check memory")):
            return IntentAnalysis(
                intent=IntentType.MEMORY_LIST,
                confidence=0.95,
                raw_query=clean,
            )

        # 4. Vision / Screen Inspection
        if any(w in lower for w in ("analyze screen", "analyze my screen", "what is on my screen", "what's on my screen", "inspect screen", "look at my screen", "screen recon")):
            return IntentAnalysis(
                intent=IntentType.VISION_INSPECT,
                confidence=0.95,
                raw_query=clean,
            )

        # 5. Workspace Macros
        if any(w in lower for w in ("dev mode", "developer mode", "setup dev", "dev workspace")):
            return IntentAnalysis(
                intent=IntentType.WORKSPACE_MACRO,
                confidence=0.95,
                raw_query=clean,
                params={"mode": "dev"},
            )
        if any(w in lower for w in ("focus mode", "tactical focus", "deep work")):
            return IntentAnalysis(
                intent=IntentType.WORKSPACE_MACRO,
                confidence=0.95,
                raw_query=clean,
                params={"mode": "focus"},
            )
        if any(w in lower for w in ("deep scan", "system scan", "diagnostics")):
            return IntentAnalysis(
                intent=IntentType.WORKSPACE_MACRO,
                confidence=0.95,
                raw_query=clean,
                params={"mode": "scan"},
            )

        # 6. Telemetry
        if any(w in lower for w in ("system status", "telemetry", "vitals", "hardware load", "system vitals")) or (
            any(w in lower for w in ("cpu", "ram", "battery", "memory usage")) and not any(w in lower for w in ("clear", "remember", "forget"))
        ):
            return IntentAnalysis(
                intent=IntentType.TELEMETRY,
                confidence=0.90,
                raw_query=clean,
            )

        # 7. Web Search
        search_match = re.search(r"(?:search\s+for|search\s+web\s+for|google|look\s+up)\s+(.+?)(?:\s+(?:and|then|,)\s+|$)", lower)
        if search_match:
            q = search_match.group(1).strip()
            if q and len(q) > 1 and q not in ("music", "spotify", "code", "it"):
                return IntentAnalysis(
                    intent=IntentType.WEB_SEARCH,
                    confidence=0.90,
                    raw_query=clean,
                    params={"query": q},
                )

        # 8. Directive Actions (App Launch / Close / Media / Network / Windows / Clipboard / Timers / IoT / Logs)
        has_launch = bool(LAUNCH_VERB_RE.search(lower))
        has_close = bool(CLOSE_VERB_RE.search(lower))
        has_media = any(w in lower for w in ("play", "pause", "volume", "louder", "quieter", "softer", "mute", "unmute", "skip", "track", "song")) or bool(
            VOLUME_SET_RE.search(lower) or VOLUME_UP_RE.search(lower) or VOLUME_DOWN_RE.search(lower)
        )
        has_iot = any(w in lower for w in (
            "iot", "smart home", "smart device", "turn on ", "turn off ", "switch on ", "switch off ",
            "toggle ", "lock the ", "unlock the ", "front door", "garage door",
        ))
        has_logs = any(w in lower for w in (
            "veronica log", "log veronica", "show log", "check log", "view log", "audit log", "security log", "recent logs",
        ))
        has_extra = any(w in lower for w in (
            "network status", "ip address", "local ip", "open windows", "active windows", "list windows",
            "focus window", "minimize ", "switch to ", "bring up ", "clipboard", "set a timer", "set timer",
            "cancel timer", "check timer", "list timer", "wipe memory", "forget ",
        ))
        if has_launch or has_close or has_media or has_iot or has_logs or has_extra:
            return IntentAnalysis(
                intent=IntentType.DIRECTIVE_ACTION,
                confidence=0.90,
                raw_query=clean,
            )

        return IntentAnalysis(
            intent=IntentType.CONVERSATION,
            confidence=0.80,
            raw_query=clean,
        )

    @staticmethod
    def _extract_app_targets(lower: str, verb_pattern: str) -> list[str]:
        """Extract known or generic app names governed by the given verb regex."""
        targets: list[str] = []
        # Check clauses separated by 'and' / 'then' / ',' so "close spotify and open notepad" routes each verb to its own object
        clauses = re.split(r"\b(?:and|then|also)\b|[,;]", lower)
        for clause in clauses:
            if not re.search(verb_pattern, clause):
                continue
            matched_known = False
            for app_id, aliases in APP_KEYWORDS_MAP.items():
                for alias in aliases:
                    if re.search(rf"\b{re.escape(alias)}\b", clause):
                        if app_id not in targets:
                            targets.append(app_id)
                        matched_known = True
                        break
            if not matched_known:
                m = re.search(rf"{verb_pattern}\s+(?:the\s+|my\s+)?([a-z0-9_\-\.]+)", clause)
                if m:
                    cand = m.group(1).strip().rstrip(".")
                    if cand not in NON_APP_TARGETS and len(cand) >= 2 and cand not in targets:
                        targets.append(cand)
        return targets

    async def execute_directives(
        self,
        clean: str,
        tool_callback: Optional[Callable[[str, dict[str, Any]], Any]] = None,
    ) -> tuple[bool, list[str], list[str]]:
        """Execute compound or single desktop directives and return action summaries."""
        lower = clean.lower()
        summaries: list[str] = []
        tools_run: list[str] = []

        # 1a. Close / Quit Applications (handled before launch so "close X and open Y" works cleanly)
        close_verb_pat = r"\b(?:force\s+close|force\s+quit|force\s+kill|close|quit|exit|kill|terminate|shut\s*down)"
        force_close = bool(re.search(r"\bforce\s+(?:close|quit|kill)\b", lower))
        close_targets = self._extract_app_targets(lower, close_verb_pat)
        for app in close_targets:
            res = close_application(app, force=force_close)
            name = _friendly_app_name(app)
            if res.get("status") == "success":
                summaries.append(f"Closed {name}")
            else:
                summaries.append(res.get("message") or f"Could not close {name}")
            tools_run.append(f"close:{app}")
            if tool_callback:
                tool_callback("close_application", {**res, "app": name})

        # 1b. Launch Applications
        launch_verb_pat = r"\b(?:open|launch|start|run|pull\s+up|fire\s+up|deploy)"
        app_targets = [
            a for a in self._extract_app_targets(lower, launch_verb_pat)
            if a not in close_targets
        ]
        # Implicit Spotify launch on "play spotify"
        if "spotify" in lower and "play" in lower and "spotify" not in app_targets and "spotify" not in close_targets:
            app_targets.append("spotify")

        for app in app_targets:
            res = launch_application(app)
            name = _friendly_app_name(app)
            if res.get("status") == "success":
                summaries.append(f"Launched {name}")
            else:
                summaries.append(res.get("message") or f"Could not find {name}")
            tools_run.append(f"launch:{app}")
            if tool_callback:
                tool_callback("launch_application", {**res, "app": name})

        # 2. Media Controls
        wants_play = any(w in lower for w in (
            "play music", "play tracks", "play song", "put some music on", "put on music",
            "start music", "resume music", "play audio", "start playback", "resume playback",
        )) or (
            bool(re.search(r"\bplay\b", lower)) and not any(w in lower for w in ("game", "youtube", "video", "role"))
        )
        if wants_play:
            spotify_running = False
            if "spotify" in app_targets:
                spotify_running = True
                await asyncio.sleep(0.3)
            else:
                try:
                    for p in psutil.process_iter(["name"]):
                        pname = p.info.get("name")
                        if pname and "spotify" in pname.lower():
                            spotify_running = True
                            break
                except Exception:
                    pass

                if not spotify_running:
                    res = launch_application("spotify")
                    if res.get("status") == "success":
                        summaries.append("Launched Spotify")
                        tools_run.append("launch:spotify")
                        if tool_callback:
                            tool_callback("launch_application", res)
                        await asyncio.sleep(0.4)

            media_control("play_pause")
            summaries.append("Started audio playback")
            tools_run.append("media:play")
            if tool_callback:
                tool_callback("media_control", {"action": "play"})

        elif any(w in lower for w in ("pause music", "stop music", "pause playback", "stop playback")) or bool(re.search(r"\bpause\b", lower)):
            media_control("play_pause")
            summaries.append("Paused playback")
            tools_run.append("media:pause")
            if tool_callback:
                tool_callback("media_control", {"action": "pause"})

        vol_set_m = VOLUME_SET_RE.search(lower)
        vol_step_up_m = VOLUME_STEP_UP_RE.search(lower)
        vol_step_down_m = VOLUME_STEP_DOWN_RE.search(lower)

        if vol_set_m:
            raw_lvl = next(g for g in vol_set_m.groups() if g is not None)
            target_lvl = max(0, min(100, int(raw_lvl)))
            vres = media_control("set_volume", level=target_lvl)
            pct = vres.get("volume_percent", target_lvl)
            summaries.append(f"Set system master volume to {pct}%")
            tools_run.append(f"media:set_volume:{pct}")
            if tool_callback:
                tool_callback("media_control", {**vres, "action": "set_volume"})
        elif any(w in lower for w in ("max volume", "maximum volume", "full volume")):
            vres = media_control("set_volume", level=100)
            summaries.append("Set system master volume to 100%")
            tools_run.append("media:set_volume:100")
            if tool_callback:
                tool_callback("media_control", {**vres, "action": "set_volume"})
        elif vol_step_up_m:
            raw_step = next(g for g in vol_step_up_m.groups() if g is not None)
            step_val = max(2, min(100, int(raw_step)))
            vres = media_control("volume_up", step=step_val)
            pct = vres.get("volume_percent")
            summaries.append(f"Amplified volume to {pct}%" if pct is not None else "Amplified volume")
            tools_run.append("media:volume_up")
            if tool_callback:
                tool_callback("media_control", {**vres, "action": "volume_up"})
        elif vol_step_down_m:
            raw_step = next(g for g in vol_step_down_m.groups() if g is not None)
            step_val = max(2, min(100, int(raw_step)))
            vres = media_control("volume_down", step=step_val)
            pct = vres.get("volume_percent")
            summaries.append(f"Reduced volume to {pct}%" if pct is not None else "Reduced volume")
            tools_run.append("media:volume_down")
            if tool_callback:
                tool_callback("media_control", {**vres, "action": "volume_down"})
        elif VOLUME_UP_RE.search(lower):
            vres = media_control("volume_up")
            pct = vres.get("volume_percent")
            summaries.append(f"Amplified volume to {pct}%" if pct is not None else "Amplified volume")
            tools_run.append("media:volume_up")
            if tool_callback:
                tool_callback("media_control", {**vres, "action": "volume_up"})
        elif VOLUME_DOWN_RE.search(lower):
            vres = media_control("volume_down")
            pct = vres.get("volume_percent")
            summaries.append(f"Reduced volume to {pct}%" if pct is not None else "Reduced volume")
            tools_run.append("media:volume_down")
            if tool_callback:
                tool_callback("media_control", {**vres, "action": "volume_down"})

        if any(w in lower for w in ("mute audio", "mute sound", "mute volume", "unmute")) or (bool(re.search(r"\bmute\b", lower)) and "focus" not in lower):
            media_control("mute")
            summaries.append("Toggled audio mute")
            tools_run.append("media:mute")
            if tool_callback:
                tool_callback("media_control", {"action": "mute"})

        if any(w in lower for w in ("next song", "next track", "skip song", "skip track", "skip")):
            media_control("next")
            summaries.append("Skipped to next track")
            tools_run.append("media:next")
            if tool_callback:
                tool_callback("media_control", {"action": "next"})
        elif any(w in lower for w in ("previous song", "previous track", "last song", "go back a track")):
            media_control("prev")
            summaries.append("Rewound to previous track")
            tools_run.append("media:prev")
            if tool_callback:
                tool_callback("media_control", {"action": "prev"})

        # 3. Workspace Macros
        if any(w in lower for w in ("dev mode", "developer mode", "setup dev", "dev workspace")):
            res = workspace_macro("dev")
            branch = res.get("branch", "master")
            summaries.append(f"Deployed dev workspace on branch '{branch}'")
            tools_run.append("workspace_macro:dev")
            if tool_callback:
                tool_callback("workspace_macro", res)

        if any(w in lower for w in ("focus mode", "tactical focus", "deep work")):
            res = workspace_macro("focus")
            summaries.append("Focus protocol engaged; audio muted")
            tools_run.append("workspace_macro:focus")
            if tool_callback:
                tool_callback("workspace_macro", res)

        if any(w in lower for w in ("deep scan", "system scan", "diagnostics")):
            res = workspace_macro("scan")
            summaries.append("Diagnostic telemetry scan completed")
            tools_run.append("workspace_macro:scan")
            if tool_callback:
                tool_callback("workspace_macro", res)

        # 4. Telemetry
        if any(w in lower for w in ("system status", "telemetry", "vitals", "hardware load", "system vitals")) or (
            any(w in lower for w in ("cpu", "ram", "battery", "memory usage")) and not any(w in lower for w in ("clear", "remember", "forget"))
        ):
            vit = get_system_telemetry()
            top_p = vit["top_processes"][0]["name"] if vit["top_processes"] else "idle"
            summaries.append(f"Telemetry check: CPU {vit['cpu_percent']}%, RAM {vit['ram_used_gb']}GB ({vit['ram_percent']}%), Chief: {top_p}")
            tools_run.append("telemetry")
            if tool_callback:
                tool_callback("telemetry", vit)

        # 5. Network Recon
        if any(w in lower for w in ("network status", "check network", "ip address", "local ip", "what is my ip")):
            net = get_network_status()
            summaries.append(f"Network status: Host {net['hostname']} at {net['local_ip']} (TX {net['bytes_sent_mb']}MB / RX {net['bytes_recv_mb']}MB)")
            tools_run.append("network_status")
            if tool_callback:
                tool_callback("network_status", net)

        # 6. Window Manager (list, focus/switch to, minimize)
        if any(w in lower for w in ("list windows", "open windows", "active windows", "what windows are open")):
            wres = window_manager("list")
            win_list = ", ".join(wres.get("windows", [])[:5]) or "Desktop"
            summaries.append(f"Active desktop windows ({wres.get('count', 0)}): {win_list}")
            tools_run.append("window_manager:list")
            if tool_callback:
                tool_callback("window_manager", wres)
        else:
            focus_m = re.search(r"^(?:focus|switch\s+to|bring\s+up)\s+(?:window\s+)?(.+)$", lower)
            min_m = re.search(r"^minimize\s+(?:window\s+)?(.+)$", lower)
            if focus_m and "focus mode" not in lower:
                tgt = focus_m.group(1).strip()
                wres = window_manager("focus", tgt)
                summaries.append(f"Focused window '{wres.get('window', tgt)}'" if wres.get("status") == "success" else wres.get("message", f"No window matching '{tgt}'"))
                tools_run.append(f"window_manager:focus:{tgt}")
                if tool_callback:
                    tool_callback("window_manager", wres)
            elif min_m:
                tgt = min_m.group(1).strip()
                wres = window_manager("minimize", tgt)
                summaries.append(f"Minimized window '{wres.get('window', tgt)}'" if wres.get("status") == "success" else wres.get("message", f"No window matching '{tgt}'"))
                tools_run.append(f"window_manager:minimize:{tgt}")
                if tool_callback:
                    tool_callback("window_manager", wres)

        # 7. Timers
        timer_match = re.search(r"set\s+(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(second|seconds|sec|minute|minutes|min)", lower)
        if timer_match:
            val = int(timer_match.group(1))
            unit = timer_match.group(2)
            secs = val * 60 if unit.startswith("min") else val
            tres = timer_reminder("set", f"{val} {unit}", secs)
            summaries.append(f"Armed tactical timer for {val} {unit}")
            tools_run.append(f"timer:{secs}")
            if tool_callback:
                tool_callback("timer_reminder", tres)
        elif any(w in lower for w in ("cancel timer", "clear timers", "stop timer")):
            tres = timer_reminder("cancel")
            summaries.append("Cleared all active timers")
            tools_run.append("timer:cancel")
            if tool_callback:
                tool_callback("timer_reminder", tres)
        elif any(w in lower for w in ("check timer", "check timers", "list timers", "active timers", "how much time left")):
            tres = timer_reminder("list")
            timers = tres.get("timers", [])
            if timers:
                desc = ", ".join(f"{t['label']} ({t['remaining_seconds']}s left)" for t in timers)
                summaries.append(f"Active timers: {desc}")
            else:
                summaries.append("No active timers running")
            tools_run.append("timer:list")
            if tool_callback:
                tool_callback("timer_reminder", tres)

        # 8. Clipboard
        copy_m = re.search(r"^copy\s+[\"']?(.+?)[\"']?\s+to\s+(?:my\s+)?clipboard$", clean, re.IGNORECASE)
        if copy_m:
            txt_to_copy = copy_m.group(1)
            cres = clipboard_tool("set", txt_to_copy)
            summaries.append(f"Copied '{txt_to_copy[:40]}' to clipboard")
            tools_run.append("clipboard:set")
            if tool_callback:
                tool_callback("clipboard_tool", cres)
        elif any(w in lower for w in ("read clipboard", "what is in my clipboard", "what's in my clipboard", "check clipboard", "show clipboard")):
            cres = clipboard_tool("get")
            clip_txt = (cres.get("content") or "").strip()
            snippet = (clip_txt[:80] + "...") if len(clip_txt) > 80 else (clip_txt or "empty")
            summaries.append(f"Clipboard contents: '{snippet}'")
            tools_run.append("clipboard:get")
            if tool_callback:
                tool_callback("clipboard_tool", cres)

        # 9. Memory Wipe / Forget
        if any(w in lower for w in ("wipe memory", "wipe all memories", "clear all memories")):
            mres = memory_store("wipe")
            summaries.append("Wiped and vacuumed all tactical memory banks")
            tools_run.append("memory:wipe")
            if tool_callback:
                tool_callback("memory", mres)
        else:
            forget_m = re.search(r"^(?:forget|delete\s+memory)\s+(?:my\s+|that\s+)?([a-zA-Z0-9_\-\s]{2,30})$", lower)
            if forget_m:
                fkey = forget_m.group(1).strip()
                mres = memory_store("delete", fkey)
                summaries.append(f"Removed '{fkey}' from tactical memory")
                tools_run.append(f"memory:delete:{fkey}")
                if tool_callback:
                    tool_callback("memory", mres)

        # 10. Web Search
        search_match = re.search(r"(?:search\s+for|search\s+web\s+for|google|look\s+up)\s+(.+?)(?:\s+(?:and|then|,)\s+|$)", lower)
        if search_match:
            q = search_match.group(1).strip()
            if q and len(q) > 1 and q not in ("music", "spotify", "code", "it"):
                search_web(q)
                summaries.append(f"Searched web for '{q}'")
                tools_run.append(f"search:{q}")
                if tool_callback:
                    tool_callback("search_web", {"query": q})

        # 11. IoT & Smart Home Security Directives
        if any(w in lower for w in ("scan iot", "scan smart devices", "discover iot", "find iot devices", "iot scan")):
            ires = iot_control("scan")
            cnt = ires.get("discovered_count", 0)
            summaries.append(f"Completed LAN IoT security scan ({cnt} local nodes discovered)")
            tools_run.append("iot:scan")
            if tool_callback:
                tool_callback("iot_control", ires)
        elif any(w in lower for w in ("list iot", "list smart devices", "iot status", "smart home status", "iot devices")):
            ires = iot_control("list")
            cnt = ires.get("count", 0)
            summaries.append(f"Retrieved {cnt} registered IoT devices (Home Assistant configured: {ires.get('home_assistant_configured')})")
            tools_run.append("iot:list")
            if tool_callback:
                tool_callback("iot_control", ires)
        else:
            iot_sw_m = re.search(
                r"\b(?:(turn\s+on|switch\s+on|enable)|(turn\s+off|switch\s+off|disable)|(toggle))\s+(?:the\s+|my\s+)?([a-z0-9_\-\s]{2,35}?(?:light|lights|lamp|led|strip|plug|switch|fan|relay|ac|heater|thermostat|iot))\b",
                lower,
            )
            iot_lock_m = re.search(
                r"\b(lock|unlock)\s+(?:the\s+|my\s+)?([a-z0-9_\-\s]{2,30}?(?:door|lock|garage|gate))\b",
                lower,
            )
            if iot_sw_m:
                act = "turn_on" if iot_sw_m.group(1) else ("turn_off" if iot_sw_m.group(2) else "toggle")
                tgt = iot_sw_m.group(4).strip()
                ires = iot_control(act, target=tgt, confirm_security=("confirm" in lower or "override" in lower))
                summaries.append(ires.get("message") or f"Executed {act} on IoT target '{tgt}'")
                tools_run.append(f"iot:{act}:{tgt}")
                if tool_callback:
                    tool_callback("iot_control", {**ires, "action": act, "target": tgt})
            elif iot_lock_m:
                act = iot_lock_m.group(1).lower()
                tgt = iot_lock_m.group(2).strip()
                ires = iot_control(act, target=tgt, confirm_security=("confirm" in lower or "override" in lower))
                summaries.append(ires.get("message") or f"Executed {act} on '{tgt}'")
                tools_run.append(f"iot:{act}:{tgt}")
                if tool_callback:
                    tool_callback("iot_control", {**ires, "action": act, "target": tgt})

        # 12. Veronica Operational & Security Audit Logs
        if any(w in lower for w in (
            "veronica log", "log veronica", "show log", "check log", "view log", "audit log", "security log", "recent logs",
        )):
            lres = get_veronica_logs(limit=15, include_audit=True)
            audit_cnt = len(lres.get("recent_audit_events", []))
            log_cnt = len(lres.get("recent_logs", []))
            summaries.append(
                f"Retrieved Veronica telemetry logs ({log_cnt} log entries, {audit_cnt} security audit events at {lres.get('log_file')})"
            )
            tools_run.append("veronica_logs")
            if tool_callback:
                tool_callback("get_veronica_logs", lres)

        return len(summaries) > 0, summaries, tools_run

    def generate_action_confirmation(self, summaries: list[str]) -> str:
        """Synthesize natural, varied Stark AI confirmations for executed actions."""
        has_spotify = any("launched spotify" in s.lower() for s in summaries)
        has_playback = any("playback" in s.lower() or "audio" in s.lower() for s in summaries)
        if has_spotify and has_playback and len(summaries) == 2:
            return random.choice([
                "Deploying Spotify and initiating audio playback now, sir.",
                "Spotify initialized, sound systems active, and music rolling, sir.",
                "Right away, sir. Spotify is active and your soundtrack is engaged.",
                "On it. Spotify launched and playback initiated.",
            ])

        closed_apps = [s.replace("Closed ", "") for s in summaries if s.startswith("Closed ")]
        if closed_apps and len(closed_apps) == len(summaries):
            apps_str = " and ".join(closed_apps)
            return random.choice([
                f"Terminated {apps_str}, sir.",
                f"{apps_str} closed and cleared from the desktop, sir.",
                f"Done, sir. {apps_str} has been shut down.",
            ])

        telemetry_items = [s for s in summaries if "Telemetry check:" in s]
        action_items = [s for s in summaries if "Telemetry check:" not in s]

        if telemetry_items and not action_items:
            stat_msg = telemetry_items[0].replace("Telemetry check: ", "")
            return f"Telemetry report: {stat_msg}. All monitors nominal, sir."

        if telemetry_items and action_items:
            stat_msg = telemetry_items[0].replace("Telemetry check: ", "")
            act_str = "; ".join(action_items)
            return f"{act_str}. Telemetry: {stat_msg}, sir."

        launched_apps = [s.replace("Launched ", "") for s in summaries if s.startswith("Launched ")]
        non_app_actions = [s for s in summaries if not s.startswith("Launched ")]

        if launched_apps and not non_app_actions:
            if len(launched_apps) > 1:
                apps_str = " and ".join(launched_apps)
                return random.choice([
                    f"Deploying {apps_str} now, sir. Workspaces active.",
                    f"Initializing {apps_str}. Processes running and ready.",
                    f"Right away, sir. {apps_str} deployed to your desktop.",
                ])
            else:
                app = launched_apps[0]
                return random.choice([
                    f"Deploying {app} now, sir.",
                    f"Initializing {app}. Process running.",
                    f"Right away, sir. {app} is live.",
                    f"On it, sir. Deploying {app}.",
                ])

        if launched_apps and non_app_actions:
            apps_str = " and ".join(launched_apps)
            non_app_str = " and ".join([a.lower() for a in non_app_actions])
            return random.choice([
                f"Deploying {apps_str} and {non_app_str}, sir.",
                f"Right away, sir. {apps_str} initialized and {non_app_str}.",
                f"On it. {apps_str} deployed; {non_app_str}.",
            ])

        if len(summaries) == 1 and any(w in summaries[0].lower() for w in ("not running", "could not", "unable to", "waiting on a prompt")):
            return f"{summaries[0]}."

        combined = ", and ".join(summaries)
        return random.choice([
            f"Operations complete: {combined}, sir.",
            f"Understood, sir. {combined}.",
            f"Confirmed. {combined}.",
        ])
