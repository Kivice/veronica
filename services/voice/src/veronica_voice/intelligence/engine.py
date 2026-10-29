"""Central Intelligence Engine orchestrator for Project Veronica."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Callable, Optional

from ..audit_logger import record_audit_event, setup_veronica_logging
from ..tools import (
    capture_screen_base64,
    get_credentials,
    memory_store,
    save_credentials,
)
from .adapters import (
    AnthropicAdapter,
    BaseModelAdapter,
    GeminiAdapter,
    GroqAdapter,
    OllamaAdapter,
    OpenAiAdapter,
    TacticalCoreAdapter,
)
from .context import ContextManager
from .intent import IntentRouter
from .models import IntentType
from .tools_schema import dispatch_tool_call, get_gemini_function_declarations
from .vision import VisionEngine

logger = logging.getLogger("veronica.intelligence.engine")


class IntelligenceEngine:
    """The core backend engine coordinating intent routing, multi-provider model fallbacks,
    circuit breakers, conversation context, and tactical tool execution.
    """

    def __init__(self, env_path: Optional[str] = None):
        setup_veronica_logging()
        creds = get_credentials()
        groq_key = os.environ.get("GROQ_API_KEY") or creds.get("groq", "")
        openai_key = os.environ.get("OPENAI_API_KEY") or creds.get("openai", "")
        gemini_key = os.environ.get("GEMINI_API_KEY") or creds.get("gemini", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or creds.get("anthropic", "")
        ollama_url = os.environ.get("OLLAMA_URL") or creds.get("ollama", "")

        # Adapters
        self.groq = GroqAdapter(api_key=groq_key)
        self.openai = OpenAiAdapter(api_key=openai_key)
        self.gemini = GeminiAdapter(api_key=gemini_key)
        self.anthropic = AnthropicAdapter(api_key=anthropic_key)
        self.ollama = OllamaAdapter(base_url=ollama_url)
        self.tactical_core = TacticalCoreAdapter()

        # Engine subsystems
        self.context = ContextManager()
        self.intent_router = IntentRouter()
        self.vision = VisionEngine(gemini_api_key=gemini_key, openai_api_key=openai_key)
        self.tool_callback: Optional[Callable[[str, dict[str, Any]], Any]] = None

    def set_tool_callback(self, callback: Optional[Callable[[str, dict[str, Any]], Any]]) -> None:
        """Register a callback for real-time notification when tools execute."""
        self.tool_callback = callback

    def update_credentials(self, keys: dict[str, str], overwrite_existing: bool = True) -> None:
        """Update provider API credentials dynamically and persist them."""
        if "groq" in keys and (overwrite_existing or not self.groq.api_key):
            self.groq.update_key(keys["groq"])
            if self.groq.api_key:
                os.environ["GROQ_API_KEY"] = self.groq.api_key
        if "openai" in keys and (overwrite_existing or not self.openai.api_key):
            self.openai.update_key(keys["openai"])
            self.vision.update_keys(openai_key=self.openai.api_key)
            if self.openai.api_key:
                os.environ["OPENAI_API_KEY"] = self.openai.api_key
        if "gemini" in keys and (overwrite_existing or not self.gemini.api_key):
            self.gemini.update_key(keys["gemini"])
            self.vision.update_keys(gemini_key=self.gemini.api_key)
            if self.gemini.api_key:
                os.environ["GEMINI_API_KEY"] = self.gemini.api_key
        if "anthropic" in keys and (overwrite_existing or not self.anthropic.api_key):
            self.anthropic.update_key(keys["anthropic"])
            if self.anthropic.api_key:
                os.environ["ANTHROPIC_API_KEY"] = self.anthropic.api_key
        if "ollama" in keys and (overwrite_existing or not self.ollama.api_key):
            self.ollama.update_key(keys["ollama"])
            if self.ollama.api_key:
                os.environ["OLLAMA_URL"] = self.ollama.api_key

        save_credentials({
            "groq": self.groq.api_key,
            "openai": self.openai.api_key,
            "gemini": self.gemini.api_key,
            "anthropic": self.anthropic.api_key,
            "ollama": self.ollama.api_key,
        })
        logger.info("Credentials updated. Active provider is now: %s", self.get_active_provider())

    def get_active_provider(self) -> str:
        """Identify which provider currently serves as primary."""
        if self.groq.is_available:
            return "Groq (Llama 3.3 70B Cloud)"
        if self.openai.is_available:
            return "OpenAI (GPT-4o Cloud)"
        if self.gemini.is_available:
            return "Google Gemini (Flash Cloud)"
        if self.anthropic.is_available:
            return "Anthropic (Claude 3.5 Cloud)"
        if self.ollama.is_available:
            return "Local Ollama"
        for a in (self.groq, self.openai, self.gemini, self.anthropic):
            if a.key_invalid:
                return f"Tactical Core ({a.provider_id.upper()} KEY INVALID)"
        return "Veronica Tactical Offline Core"

    def get_provider_pipeline(self) -> list[BaseModelAdapter]:
        """Ordered list of providers for query execution with automatic failover."""
        pipeline: list[BaseModelAdapter] = []
        if self.groq.is_available:
            pipeline.append(self.groq)
        if self.openai.is_available:
            pipeline.append(self.openai)
        if self.gemini.is_available:
            pipeline.append(self.gemini)
        if self.anthropic.is_available:
            pipeline.append(self.anthropic)
        if self.ollama.is_available:
            pipeline.append(self.ollama)
        pipeline.append(self.tactical_core)
        return pipeline

    async def _handle_memory_intent(self, intent_analysis) -> Optional[AsyncIterator[str]]:
        """Handles fast-path memory operations using SQLite + FTS5 without external LLM latency."""
        if intent_analysis.intent == IntentType.MEMORY_STORE:
            key = intent_analysis.params.get("key", "")
            val = intent_analysis.params.get("value", "")
            if key and val:
                memory_store("set", key, val)

                async def _stream_reply():
                    reply = f"Acknowledged, sir. I have committed '{key}' = '{val}' to tactical memory banks. It is permanently retained across sessions."
                    for word in reply.split(" "):
                        yield word + " "
                        await asyncio.sleep(0.015)

                return _stream_reply()

        elif intent_analysis.intent == IntentType.MEMORY_QUERY:
            key = intent_analysis.params.get("key", "")
            res = memory_store("get", key)
            val = res.get("value")
            if val is None:
                # FTS5 full-text search fallback
                fts_res = memory_store("search", key)
                matches = fts_res.get("matches", {})
                if matches:
                    first_k = next(iter(matches))
                    key = first_k
                    val = matches[first_k]

            if val is not None:
                async def _stream_query_reply():
                    reply = f"Tactical memory query confirmed: your {key} is '{val}'."
                    for word in reply.split(" "):
                        yield word + " "
                        await asyncio.sleep(0.015)

                return _stream_query_reply()

        elif intent_analysis.intent == IntentType.MEMORY_LIST:
            all_notes = memory_store("list").get("notes", {})

            async def _stream_list_reply():
                if not all_notes:
                    reply = "Tactical memory banks are currently empty. You can store any directive or fact by saying 'remember that [key] is [value]'."
                else:
                    items = ", ".join([f"{k} = '{v}'" for k, v in all_notes.items()])
                    reply = f"Active tactical memory records: {items}. All records are indexed in FTS5 memory banks."
                for word in reply.split(" "):
                    yield word + " "
                    await asyncio.sleep(0.015)

            return _stream_list_reply()

        return None

    def _build_action_prompt(self, user_text: str, summaries: list[str]) -> str:
        ops = "\n".join([f"- {s}" for s in summaries])
        return (
            f"User Directive: '{user_text}'\n\n"
            f"[SYSTEM ACTION EXECUTION NOTICE]:\n"
            f"The following desktop operations were just executed live on Windows:\n"
            f"{ops}\n\n"
            f"INSTRUCTION: Acknowledge the execution stylishly, naturally, and concisely in 1 to 2 sentences max in your signature Veronica personality (Stark Industries tactical AI). "
            f"Do NOT repeat the user's prompt verbatim. Sound in effortless command of the desktop."
        )

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Main streaming entry point: classifies intent, executes fast-path directives,
        and streams through the optimal provider with automated fallback.
        """
        clean = user_text.strip()
        if not clean:
            return

        # 1. Intent Classification
        analysis = self.intent_router.classify(clean)
        logger.info("User input classified: intent=%s query='%s'", analysis.intent.value, clean[:120])

        # 2. Memory fast-path check
        mem_stream = await self._handle_memory_intent(analysis)
        if mem_stream is not None:
            full_reply: list[str] = []
            async for chunk in mem_stream:
                full_reply.append(chunk)
                yield chunk
            reply_text = "".join(full_reply).strip()
            if reply_text:
                self.context.add_user_message(clean)
                self.context.add_assistant_message(reply_text)
            return

        # 2b. Vision / Screen Recon fast-path check
        if analysis.intent == IntentType.VISION_INSPECT:
            img_b64 = capture_screen_base64() or "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            vis_reply: list[str] = []
            async for chunk in self.analyze_screen(img_b64, prompt=clean):
                vis_reply.append(chunk)
                yield chunk
            reply_text = "".join(vis_reply).strip()
            if reply_text:
                self.context.add_user_message(clean)
                self.context.add_assistant_message(reply_text)
            return

        # 3. Desktop Directives (Compound Actions, App Launch, Media, Macros, Telemetry, Network, Windows, Timers)
        actions_executed, summaries, tools_run = await self.intent_router.execute_directives(
            clean,
            tool_callback=self.tool_callback,
        )
        if actions_executed:
            record_audit_event(
                "directive.executed",
                status="success",
                details={"query": clean[:120], "tools": tools_run, "summaries": summaries},
            )

        pipeline = self.get_provider_pipeline()
        full_chunks: list[str] = []
        success = False

        if actions_executed:
            cloud_available = any(a.is_available and a != self.tactical_core for a in pipeline)
            if not cloud_available:
                confirm_text = self.intent_router.generate_action_confirmation(summaries)
                for word in confirm_text.split(" "):
                    full_chunks.append(word + " ")
                    yield word + " "
                    await asyncio.sleep(0.015)
                success = True
            else:
                action_prompt = self._build_action_prompt(clean, summaries)
                sys_prompt = self.context.build_system_prompt()
                messages = self.context.get_messages_for_provider(new_prompt=action_prompt)

                for adapter in pipeline:
                    if adapter == self.tactical_core:
                        continue
                    try:
                        full_chunks.clear()
                        async for chunk in adapter.stream_chat(messages, system_prompt=sys_prompt):
                            full_chunks.append(chunk)
                            yield chunk
                        success = True
                        break
                    except Exception as exc:
                        logger.warning("Adapter '%s' failed for action response: %s", adapter.name, exc)
                        continue

                if not success:
                    confirm_text = self.intent_router.generate_action_confirmation(summaries)
                    for word in confirm_text.split(" "):
                        full_chunks.append(word + " ")
                        yield word + " "
                        await asyncio.sleep(0.015)
                    success = True
        else:
            sys_prompt = self.context.build_system_prompt()
            messages = self.context.get_messages_for_provider(new_prompt=clean)
            gemini_tools = get_gemini_function_declarations()

            def _agentic_tool_exec(fn_name: str, fn_args: dict[str, Any]) -> dict[str, Any]:
                res = dispatch_tool_call(fn_name, fn_args)
                record_audit_event("agentic_tool", fn_name, res.get("status", "success"), {"args": fn_args})
                if self.tool_callback:
                    try:
                        self.tool_callback(fn_name, res)
                    except Exception:
                        pass
                return res

            for adapter in pipeline:
                try:
                    full_chunks.clear()
                    async for chunk in adapter.stream_chat(
                        messages,
                        system_prompt=sys_prompt,
                        tools=gemini_tools,
                        tool_executor=_agentic_tool_exec,
                    ):
                        full_chunks.append(chunk)
                        yield chunk
                    success = True
                    break
                except Exception as exc:
                    logger.warning("Adapter '%s' failed, attempting fallback: %s", adapter.name, exc)
                    continue

        reply_text = "".join(full_chunks).strip()
        if success and reply_text:
            self.context.add_user_message(clean)
            self.context.add_assistant_message(reply_text)

    async def analyze_screen(self, image_base64: str, prompt: str = "") -> AsyncIterator[str]:
        """Multimodal screen inspection using Gemini Flash, OpenAI, or local telemetry reconnaissance."""
        sys_prompt = self.context.build_system_prompt(include_vitals_alert=False)
        async for chunk in self.vision.analyze(image_base64, prompt=prompt, system_prompt=sys_prompt):
            yield chunk

    def get_engine_status(self) -> dict[str, Any]:
        """Comprehensive diagnostic status of all providers, circuit breakers, and context metrics."""
        providers_status = [
            self.groq.to_status_dict(),
            self.openai.to_status_dict(),
            self.gemini.to_status_dict(),
            self.anthropic.to_status_dict(),
            self.ollama.to_status_dict(),
            self.tactical_core.to_status_dict(),
        ]
        mem = memory_store("list")
        notes_count = len(mem.get("notes", {}))

        return {
            "active_provider": self.get_active_provider(),
            "providers": providers_status,
            "history_turns": len(self.context.history),
            "memory_records_count": notes_count,
        }
