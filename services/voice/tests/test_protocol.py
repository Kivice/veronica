import json

import pytest

from veronica_voice.protocol import MAX_FRAME_BYTES, Envelope, ProtocolError, parse_client_frame


def frame(**kw):
    base = {"v": 1, "id": "1", "type": "ping", "payload": {}}
    base.update(kw)
    return json.dumps(base)


def test_valid_ping():
    env = parse_client_frame(frame())
    assert env.type == "ping" and env.id == "1"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        frame(v=2),
        frame(type="shell.exec"),
        frame(type="ready"),  # server-only type must not be accepted from a client
        frame(id=123),
        frame(id="x" * 129),
        frame(payload=[]),
        pytest.param(b"\x00\x01", id="binary"),
        pytest.param("x" * (MAX_FRAME_BYTES + 1), id="oversized"),
    ],
)
def test_rejects_bad_frames(raw):
    with pytest.raises(ProtocolError):
        parse_client_frame(raw)


def test_envelope_roundtrip_is_compact_json():
    out = Envelope("pong", "7").to_json()
    assert json.loads(out) == {"v": 1, "id": "7", "type": "pong", "payload": {}}
    assert " " not in out
