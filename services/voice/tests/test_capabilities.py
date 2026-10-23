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


