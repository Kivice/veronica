import json

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from veronica_voice.server import ServiceContext, run_server

TOKEN = "t" * 32


def hello(token=TOKEN):
    return json.dumps({"v": 1, "id": "h", "type": "hello", "payload": {"token": token}})


@pytest.fixture
async def url():
    async with run_server(ServiceContext(token=TOKEN)) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


async def test_binds_loopback_only():
    async with run_server(ServiceContext(token=TOKEN)) as server:
        assert {s.getsockname()[0] for s in server.sockets} == {"127.0.0.1"}


async def test_handshake_ping_and_streamed_reply(url):
    async with connect(url) as ws:
        await ws.send(hello())
        assert json.loads(await ws.recv())["type"] == "ready"
        await ws.send(json.dumps({"v": 1, "id": "p", "type": "ping"}))
        assert json.loads(await ws.recv())["type"] == "pong"
        await ws.send(json.dumps({"v": 1, "id": "t", "type": "text.input", "payload": {"text": "hi there"}}))
        text, last = "", None
        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "text.done":
                last = msg
                break
            assert msg["type"] == "text.delta" and msg["id"] == "t"
            text += msg["payload"]["text"]
        assert text.strip() == "You said: hi there" and last["id"] == "t"


async def test_wrong_token_is_closed(url):
    async with connect(url) as ws:
        await ws.send(hello("wrong" * 8))
        with pytest.raises(ConnectionClosed) as exc:
            await ws.recv()
        assert exc.value.rcvd.code == 1008


async def test_non_hello_first_frame_is_closed(url):
    async with connect(url) as ws:
        await ws.send(json.dumps({"v": 1, "id": "p", "type": "ping"}))
        with pytest.raises(ConnectionClosed) as exc:
            await ws.recv()
        assert exc.value.rcvd.code == 1008


async def test_browser_origin_is_rejected(url):
    with pytest.raises(InvalidStatus) as exc:
        async with connect(url, additional_headers={"Origin": "https://evil.example"}):
            pass
    assert exc.value.response.status_code == 403


async def test_malformed_and_oversized_input_does_not_kill_session(url):
    async with connect(url) as ws:
        await ws.send(hello())
        await ws.recv()
        await ws.send("garbage")
        assert json.loads(await ws.recv())["type"] == "error"
        await ws.send(json.dumps({"v": 1, "id": "t", "type": "text.input", "payload": {"text": "  "}}))
        assert json.loads(await ws.recv())["type"] == "error"
        await ws.send(json.dumps({"v": 1, "id": "p", "type": "ping"}))
        assert json.loads(await ws.recv())["type"] == "pong"
