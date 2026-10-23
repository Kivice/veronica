"""Loopback-only WebSocket service with real Veronica intelligence, neural TTS, and tool execution.

Security posture (see docs/THREAT_MODEL.md):
  * binds 127.0.0.1 only;
  * first frame must be `hello` carrying the per-launch secret token (constant-time compared);
  * browser-originated connections from foreign domains (Origin != loopback/null) are rejected with 403;
  * all inbound frames are size- and shape-validated;
  * live desktop execution runs with explicit feedback.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from .adapters import EchoLlm, LlmAdapter
from .brain import VeronicaBrain
from .protocol import (
    MAX_FRAME_BYTES,
    MAX_TEXT_CHARS,
    PROTOCOL_VERSION,
    Envelope,
    ProtocolError,
    parse_client_frame,
)
from .tools import execute_tool, get_system_telemetry
from .tts import AVAILABLE_VOICES, EdgeTtsEngine

logger = logging.getLogger("veronica.server")

HELLO_TIMEOUT_S = 5.0
POLICY_VIOLATION = 1008


@dataclass
class ServiceContext:
    token: str
    llm: Any = field(default_factory=EchoLlm)
    tts: Optional[EdgeTtsEngine] = None
    allowed_origins: frozenset[str] = frozenset()


def _reject_foreign_origin(ctx: ServiceContext):
    def process_request(connection: ServerConnection, request: Request) -> Response | None:
        origin = request.headers.get("Origin")
        if origin is not None:
            if origin in ctx.allowed_origins:
                return None
            # Allow loopback / local origins for UI web and desktop client
            if any(
                origin == prefix or origin.startswith(prefix + ":")
                for prefix in ("http://127.0.0.1", "http://localhost", "https://127.0.0.1", "https://localhost")
            ):
                return None
            if origin in ("null", "file://"):
                return None
            return connection.respond(403, "origin not allowed\n")
        return None

    return process_request


async def _send(ws: ServerConnection, env: Envelope) -> None:
    await ws.send(env.to_json())


def _make_handler(ctx: ServiceContext):
    async def handler(ws: ServerConnection) -> None:
        try:
            raw = await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT_S)
            hello = parse_client_frame(raw)
            supplied = str(hello.payload.get("token", ""))
            if hello.type != "hello" or not hmac.compare_digest(
                supplied.encode(), ctx.token.encode()
            ):
                await ws.close(POLICY_VIOLATION, "unauthorized")
                return
        except (asyncio.TimeoutError, ProtocolError, ConnectionClosed):
            await ws.close(POLICY_VIOLATION, "unauthorized")
            return

        active_provider = (
            ctx.llm.get_active_provider()
            if hasattr(ctx.llm, "get_active_provider")
            else "echo"
        )
        current_voice = getattr(ctx.tts, "voice", "en-US-AvaNeural") if ctx.tts else "none"

        await _send(
            ws,
            Envelope(
                "ready",
                hello.id,
                {
                    "protocol": PROTOCOL_VERSION,
                    "llm": active_provider,
                    "voice": current_voice,
                    "voices": AVAILABLE_VOICES,
                },
            ),
        )

        async for raw in ws:
            try:
                env = parse_client_frame(raw)
            except ProtocolError as exc:
                await _send(ws, Envelope("error", "", {"message": str(exc)}))
                continue

            if env.type == "ping":
                await _send(ws, Envelope("pong", env.id))

            elif env.type == "text.input":
                text = env.payload.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
                    await _send(ws, Envelope("error", env.id, {"message": "invalid text"}))
                    continue

                full_reply: list[str] = []
                async for chunk in ctx.llm.respond(text):
                    full_reply.append(chunk)
                    await _send(ws, Envelope("text.delta", env.id, {"text": chunk}))
                await _send(ws, Envelope("text.done", env.id))

                # If TTS synthesis is active and engine present, stream neural audio
                synthesize = env.payload.get("synthesize", True)
                full_text = "".join(full_reply).strip()
                if synthesize and full_text and ctx.tts is not None:
                    try:
                        async for audio_chunk in ctx.tts.stream_audio(full_text):
                            await _send(
                                ws,
                                Envelope("audio.delta", env.id, {"audio": audio_chunk, "format": "mp3"}),
                            )
                        await _send(ws, Envelope("audio.done", env.id))
                    except Exception as exc:
                        logger.warning("TTS generation skipped: %s", exc)

            elif env.type == "tool.execute":
                tool_name = str(env.payload.get("tool", ""))
                params = env.payload.get("params", {})
                result = execute_tool(tool_name, params)
                await _send(ws, Envelope("tool.result", env.id, {"tool": tool_name, "result": result}))

            elif env.type == "state.query":
                telemetry = get_system_telemetry()
                provider = (
                    ctx.llm.get_active_provider()
                    if hasattr(ctx.llm, "get_active_provider")
                    else "echo"
                )
                voice = getattr(ctx.tts, "voice", "en-US-AvaNeural") if ctx.tts else "none"
                await _send(
                    ws,
                    Envelope(
                        "telemetry",
                        env.id,
                        {
                            "telemetry": telemetry,
                            "provider": provider,
                            "voice": voice,
                            "voices": AVAILABLE_VOICES,
                        },
                    ),
                )

            elif env.type == "tts.request":
                text_to_speak = str(env.payload.get("text", "")).strip()
                if text_to_speak and ctx.tts:
                    async for audio_chunk in ctx.tts.stream_audio(text_to_speak):
                        await _send(
                            ws,
                            Envelope("audio.delta", env.id, {"audio": audio_chunk, "format": "mp3"}),
                        )
                    await _send(ws, Envelope("audio.done", env.id))

            elif env.type == "settings.update":
                keys = env.payload.get("keys", {})
                if hasattr(ctx.llm, "update_keys"):
                    ctx.llm.update_keys(keys)
                voice = env.payload.get("voice")
                if voice and hasattr(ctx.tts, "set_voice"):
                    ctx.tts.set_voice(voice)
                provider = (
                    ctx.llm.get_active_provider()
                    if hasattr(ctx.llm, "get_active_provider")
                    else "echo"
                )
                await _send(
                    ws,
                    Envelope(
                        "status",
                        env.id,
                        {
                            "message": "Configuration updated",
                            "provider": provider,
                            "voice": getattr(ctx.tts, "voice", ""),
                        },
                    ),
                )

            else:
                await _send(ws, Envelope("error", env.id, {"message": "unexpected message"}))

    return handler


def run_server(ctx: ServiceContext, port: int = 0):
    """Return an async context manager for the server (host is fixed to loopback)."""
    return serve(
        _make_handler(ctx),
        "127.0.0.1",
        port,
        max_size=MAX_FRAME_BYTES,
        process_request=_reject_foreign_origin(ctx),
    )


async def amain() -> None:
    token = os.environ.get("VERONICA_TOKEN", "")
    if len(token) < 16:
        # Generate an ephemeral secure token if not supplied
        import secrets
        token = secrets.token_hex(24)
        print(f"VERONICA_AUTH_TOKEN={token}", flush=True)

    requested_port = int(os.environ.get("VERONICA_PORT", "8765"))

    # Use the real multi-provider brain and real neural TTS engine
    ctx = ServiceContext(
        token=token,
        llm=VeronicaBrain(),
        tts=EdgeTtsEngine(voice="en-US-AvaNeural"),
    )

    async with run_server(ctx, port=requested_port) as server:
        port = server.sockets[0].getsockname()[1]
        print(
            json.dumps({"event": "listening", "host": "127.0.0.1", "port": port, "token": token}),
            flush=True,
        )
        await server.serve_forever()
