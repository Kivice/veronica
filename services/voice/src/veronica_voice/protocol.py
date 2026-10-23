"""Wire protocol between the shell/UI and the voice service (protocol version 1).

Every message is one JSON text frame:  {"v": 1, "id": str, "type": str, "payload": object}
Kept stdlib-only so it can be unit-tested without any third-party package.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 1024 * 1024  # 1 MB to accommodate compressed screen snapshots
MAX_TEXT_CHARS = 32_000

# Client -> service
CLIENT_TYPES = frozenset({
    "hello",
    "ping",
    "text.input",
    "tool.execute",
    "tts.request",
    "settings.update",
    "state.query",
    "screen.analyze",
})
# Service -> client
SERVER_TYPES = frozenset({
    "ready",
    "pong",
    "text.delta",
    "text.done",
    "audio.delta",
    "audio.done",
    "tool.result",
    "telemetry",
    "status",
    "error",
})


class ProtocolError(ValueError):
    """Raised for malformed or oversized frames. The message is safe to send to the client."""


@dataclass(frozen=True)
class Envelope:
    type: str
    id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    v: int = PROTOCOL_VERSION

    def to_json(self) -> str:
        return json.dumps(
            {"v": self.v, "id": self.id, "type": self.type, "payload": self.payload},
            separators=(",", ":"),
        )


def parse_client_frame(raw: str | bytes) -> Envelope:
    """Validate an inbound frame. Never trusts the client: size, shape and type are all checked."""
    if isinstance(raw, bytes):
        raise ProtocolError("binary frames are not supported in protocol v1")
    if len(raw.encode("utf-8")) > MAX_FRAME_BYTES:
        raise ProtocolError("frame too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ProtocolError("frame is not valid JSON") from None
    if not isinstance(data, dict):
        raise ProtocolError("frame must be a JSON object")
    if data.get("v") != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version (expected {PROTOCOL_VERSION})")
    msg_type = data.get("type")
    if msg_type not in CLIENT_TYPES:
        raise ProtocolError("unknown message type")
    msg_id = data.get("id", "")
    if not isinstance(msg_id, str) or len(msg_id) > 128:
        raise ProtocolError("id must be a string of at most 128 characters")
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be an object")
    return Envelope(type=msg_type, id=msg_id, payload=payload)
