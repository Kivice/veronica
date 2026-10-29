import json
import pytest
from veronica_voice.brain import VeronicaBrain
from veronica_voice.server import ServiceContext, run_server
from veronica_voice.tools import execute_tool, get_system_telemetry, memory_store
from veronica_voice.tts import AVAILABLE_VOICES, EdgeTtsEngine
from websockets.asyncio.client import connect

TOKEN = "v" * 32


@pytest.mark.asyncio
async def test_brain_tactical_telemetry_intent():
    brain = VeronicaBrain()
    chunks = []
    async for chunk in brain.respond("check system telemetry and cpu"):
        chunks.append(chunk)
    reply = "".join(chunks)
    assert "telemetry" in reply.lower() or "cpu" in reply.lower()


@pytest.mark.asyncio
async def test_brain_identity():
    brain = VeronicaBrain()
    chunks = []
    async for chunk in brain.respond("Who are you?"):
        chunks.append(chunk)
    reply = "".join(chunks)
    assert "veronica" in reply.lower()


def test_tools_system_telemetry():
    vitals = get_system_telemetry()
    assert "cpu_percent" in vitals
    assert "ram_percent" in vitals
    assert "battery" in vitals
    assert isinstance(vitals["top_processes"], list)


def test_tools_memory_store():
    res = memory_store("set", "mission", "Operation Veronica")
    assert res["status"] == "success"
    check = memory_store("get", "mission")
    assert check["value"] == "Operation Veronica"


def test_tts_voices_list():
    assert len(AVAILABLE_VOICES) >= 3
    engine = EdgeTtsEngine()
    assert engine.voice == "en-US-AvaNeural"


@pytest.mark.asyncio
async def test_server_state_query():
    ctx = ServiceContext(token=TOKEN, llm=VeronicaBrain(), tts=EdgeTtsEngine())
    async with run_server(ctx) as server:
        port = server.sockets[0].getsockname()[1]
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            # Authenticate
            await ws.send(json.dumps({"v": 1, "id": "h", "type": "hello", "payload": {"token": TOKEN}}))
            ready = json.loads(await ws.recv())
            assert ready["type"] == "ready"

            # Query state
            await ws.send(json.dumps({"v": 1, "id": "sq", "type": "state.query"}))
            telemetry_msg = json.loads(await ws.recv())
            assert telemetry_msg["type"] == "telemetry"
            assert "cpu_percent" in telemetry_msg["payload"]["telemetry"]

            # Direct tool execution
            await ws.send(json.dumps({
                "v": 1,
                "id": "te",
                "type": "tool.execute",
                "payload": {"tool": "system_status", "params": {}},
            }))
            tool_res = json.loads(await ws.recv())
            assert tool_res["type"] == "tool.result"
            assert "ram_total_gb" in tool_res["payload"]["result"]


@pytest.mark.asyncio
async def test_workspace_macro_and_screen_vision():
    from veronica_voice.tools import workspace_macro
    macro = workspace_macro("scan")
    assert macro["status"] == "success"
    assert "telemetry" in macro

    brain = VeronicaBrain()
    # Test tactical offline screen inspection
    chunks = []
    async for chunk in brain.analyze_screen("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="):
        chunks.append(chunk)
    analysis = "".join(chunks)
    assert "reconnaissance" in analysis.lower() or "display" in analysis.lower()


@pytest.mark.asyncio
async def test_wake_word_and_window_commands():
    import json
    import websockets
    from veronica_voice.server import ServiceContext, run_server

    ctx = ServiceContext(token="test-secret-token")
    async with run_server(ctx, port=0) as server:
        port = server.sockets[0].getsockname()[1]
        uri = f"ws://127.0.0.1:{port}"

        # Client 1: Represents the Tray Controller
        async with websockets.connect(uri) as ws_tray:
            await ws_tray.send(json.dumps({"v": 1, "id": "1", "type": "hello", "payload": {"token": "test-secret-token"}}))
            ready_tray = json.loads(await ws_tray.recv())
            assert ready_tray["type"] == "ready"

            # Client 2: Represents the Desktop HUD
            async with websockets.connect(uri) as ws_hud:
                await ws_hud.send(json.dumps({"v": 1, "id": "2", "type": "hello", "payload": {"token": "test-secret-token"}}))
                ready_hud = json.loads(await ws_hud.recv())
                assert ready_hud["type"] == "ready"

                # HUD emits wake_word.detected
                await ws_hud.send(json.dumps({
                    "v": 1,
                    "id": "wake-1",
                    "type": "wake_word.detected",
                    "payload": {"phrase": "hey veronica"}
                }))

                # Tray receives the wake-word notification and command to show mini HUD
                tray_event1 = json.loads(await ws_tray.recv())
                assert tray_event1["type"] == "wake_word.detected"
                tray_event2 = json.loads(await ws_tray.recv())
                assert tray_event2["type"] == "window.command"
                assert tray_event2["payload"]["action"] == "show_mini"

                # HUD requests window command to switch to full deck
                await ws_hud.send(json.dumps({
                    "v": 1,
                    "id": "cmd-1",
                    "type": "window.command",
                    "payload": {"action": "show_full"}
                }))

                tray_event3 = json.loads(await ws_tray.recv())
                assert tray_event3["type"] == "window.command"
                assert tray_event3["payload"]["action"] == "show_full"


def test_sqlite_fts5_memory_bank_and_vacuum_wipe(tmp_path):
    from veronica_voice.memory_db import TacticalMemoryBank

    db_file = tmp_path / "test_mem.db"
    json_file = tmp_path / "test_mem.json"
    bank = TacticalMemoryBank(db_path=db_file, json_path=json_file)

    bank.set("armor_protocol", "Hulkbuster orbital satellite")
    bank.set("workshop_code", "Alpha-9921-Gamma")

    assert bank.get("armor_protocol") == "Hulkbuster orbital satellite"

    # FTS5 full-text search across value tokens
    fts_hits = bank.search("orbital")
    assert "armor_protocol" in fts_hits

    # Secure wipe + VACUUM leaves no recoverable rows
    bank.wipe()
    assert bank.list_all() == {}
    raw_bytes = db_file.read_bytes()
    assert b"Alpha-9921-Gamma" not in raw_bytes


@pytest.mark.asyncio
async def test_mark_v_tools_and_offline_tactical_core():
    from veronica_voice.tools import get_network_status, timer_reminder, window_manager

    net = get_network_status()
    assert net["status"] == "success"
    assert "local_ip" in net

    wres = window_manager("list")
    assert wres["status"] == "success"
    assert isinstance(wres["windows"], list)

    tres = timer_reminder("set", "test_timer", 30)
    assert tres["status"] == "success"
    tlist = timer_reminder("list")
    assert tlist["count"] >= 1
    timer_reminder("cancel", "test_timer")

    brain = VeronicaBrain()
    math_chunks = []
    async for chunk in brain.respond("calculate 12 * 12"):
        math_chunks.append(chunk)
    assert "144" in "".join(math_chunks)


@pytest.mark.asyncio
async def test_close_application_and_intent_routing():
    from veronica_voice.intelligence.intent import IntentRouter
    from veronica_voice.tools import close_application

    router = IntentRouter()
    for phrase in ("close spotify", "quit chrome", "exit notepad", "force close vscode"):
        analysis = router.classify(phrase)
        assert analysis.intent.value == "directive_action"

    # Extract targets for compound directive
    close_t = router._extract_app_targets("close spotify and open notepad", r"\b(?:close|quit)")
    open_t = router._extract_app_targets("close spotify and open notepad", r"\b(?:open|launch)")
    assert close_t == ["spotify"]
    assert open_t == ["notepad"]

    # Non-running dummy process returns clean not-running message
    res = close_application("nonexistent_app_xyz_999")
    assert res["status"] == "error"
    assert "not running" in res["message"].lower()

    # Protected system processes are never touched
    res_sys = close_application("explorer")
    assert res_sys["status"] == "error"


@pytest.mark.asyncio
async def test_volume_increase_and_exact_level_directives(monkeypatch):
    from veronica_voice.intelligence import intent as intent_mod
    from veronica_voice.intelligence.intent import IntentRouter

    recorded_calls = []

    def fake_media_control(action: str, level=None, step: int = 12):
        recorded_calls.append((action, level, step))
        return {"status": "success", "action": action, "volume_percent": level if level is not None else 60}

    monkeypatch.setattr(intent_mod, "media_control", fake_media_control)
    router = IntentRouter()

    for phrase in (
        "volume increase",
        "increase volume",
        "increase the volume",
        "turn up the volume",
        "turn the volume up",
        "volume up",
    ):
        recorded_calls.clear()
        executed, summaries, tools_run = await router.execute_directives(phrase)
        assert executed is True, f"Failed on phrase: {phrase}"
        assert recorded_calls[0][0] == "volume_up"
        assert "media:volume_up" in tools_run

    for phrase in ("volume decrease", "decrease the volume", "turn down the volume", "lower volume"):
        recorded_calls.clear()
        executed, summaries, tools_run = await router.execute_directives(phrase)
        assert executed is True, f"Failed on phrase: {phrase}"
        assert recorded_calls[0][0] == "volume_down"

    recorded_calls.clear()
    executed, summaries, tools_run = await router.execute_directives("set volume to 65%")
    assert executed is True
    assert recorded_calls[0] == ("set_volume", 65, 12)


def test_iot_security_ssrf_and_lock_gate():
    from veronica_voice.iot import iot_control, is_safe_iot_endpoint

    # RFC1918 LAN endpoints are allowed
    assert is_safe_iot_endpoint("http://192.168.1.50/rpc/Switch.Set") is True

    # Public WAN IPs are blocked (anti-SSRF)
    assert is_safe_iot_endpoint("http://8.8.8.8/api/webhook") is False

    # Registering a device with a public IP is rejected
    reg_bad = iot_control("register", target="bad_wan_plug", protocol="shelly", endpoint="http://1.1.1.1")
    assert reg_bad["status"] in ("blocked", "error")

    # High-risk physical lock actions require explicit confirmation
    lock_gate = iot_control("unlock", target="front door", confirm_security=False)
    assert lock_gate["status"] == "confirmation_required"


def test_veronica_audit_logger_redaction():
    from veronica_voice.audit_logger import get_veronica_logs, record_audit_event, redact_secrets

    fake_key = "AIza" + "S" * 30
    sample = f"Authorization: Bearer {fake_key}"
    redacted = redact_secrets(sample)
    assert fake_key not in redacted
    assert "[REDACTED]" in redacted

    ev = record_audit_event("test.security_check", status="success", details={"token": fake_key})
    assert fake_key not in json.dumps(ev)

    logs = get_veronica_logs(limit=10, include_audit=True)
    assert logs["status"] == "success"
    assert len(logs["recent_audit_events"]) >= 1


@pytest.mark.asyncio
async def test_agentic_browsing_and_core_app_interactions(monkeypatch, tmp_path):
    import webbrowser
    from veronica_voice import tools as tools_mod
    from veronica_voice.intelligence import intent as intent_mod
    from veronica_voice.intelligence.intent import IntentRouter
    from veronica_voice.intelligence.tools_schema import get_gemini_function_declarations

    opened_urls: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda u: opened_urls.append(u) or True)

    router = IntentRouter()

    # 1. Website navigation ("browse to github.com", "open youtube")
    executed, summaries, tools_run = await router.execute_directives("browse to github.com")
    assert executed is True
    assert any("github.com" in u for u in opened_urls)

    opened_urls.clear()
    executed, summaries, tools_run = await router.execute_directives("open youtube")
    assert executed is True
    assert any("youtube.com" in u for u in opened_urls)

    # 2. Site-specific search ("search github for veronica")
    opened_urls.clear()
    monkeypatch.setattr(tools_mod, "_fetch_live_web_snippets", lambda q, max_results=4: [{"title": "Veronica", "snippet": "Stark HUD", "url": "https://github.com/Kivice/veronica"}])
    executed, summaries, tools_run = await router.execute_directives("search github for veronica")
    assert executed is True
    assert any("github.com/search" in u for u in opened_urls)

    # 3. Core app interaction: Notepad note creation (mock Popen so no real window spawns during pytest)
    spawned_cmds: list[list[str]] = []
    monkeypatch.setattr(tools_mod.subprocess, "Popen", lambda cmd, **kw: spawned_cmds.append(cmd))
    executed, summaries, tools_run = await router.execute_directives("open notepad and write buy milk and eggs")
    assert executed is True
    assert "app_interact:notepad" in tools_run
    assert any("notepad.exe" in c[0] for c in spawned_cmds)

    # 4. Gemini function declarations include browser_agent and app_interact
    decls = get_gemini_function_declarations()
    names = {d["name"] for d in decls}
    assert "browser_agent" in names
    assert "app_interact" in names






