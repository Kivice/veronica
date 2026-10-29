"""Unit tests for the Veronica Intelligence Backend Engine subsystem."""
import pytest
import time
from veronica_voice.intelligence.circuit_breaker import CircuitBreaker
from veronica_voice.intelligence.context import ContextManager, redact_sensitive_data
from veronica_voice.intelligence.engine import IntelligenceEngine
from veronica_voice.intelligence.intent import IntentRouter
from veronica_voice.intelligence.models import CircuitState, IntentType
from veronica_voice.intelligence.tools_schema import TOOL_SCHEMAS, dispatch_tool_call


def test_circuit_breaker_lifecycle():
    breaker = CircuitBreaker("test-provider", failure_threshold=2, recovery_timeout_s=0.2)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_execute() is True

    # 1st failure
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.metrics.consecutive_failures == 1

    # 2nd failure -> Trips OPEN
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.can_execute() is False

    # Wait for recovery timeout
    time.sleep(0.25)
    assert breaker.can_execute() is True
    assert breaker.state == CircuitState.HALF_OPEN

    # Success in half open -> resets to CLOSED
    breaker.record_success(ttft_ms=120.0, tokens_count=15)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.metrics.consecutive_failures == 0
    assert breaker.metrics.last_ttft_ms == 120.0


def test_context_manager_redaction_and_trimming():
    ctx = ContextManager(max_history_turns=4, token_budget=100)

    # Sensitive key redaction
    fake_groq = "gsk_" + "a" * 25
    fake_oai = "sk-" + "b" * 25
    raw = f"My Groq key is {fake_groq} and OpenAI is {fake_oai}"
    redacted = redact_sensitive_data(raw)
    assert "gsk_" not in redacted
    assert "sk-" not in redacted
    assert "[REDACTED_CREDENTIAL]" in redacted

    # History turns
    for i in range(10):
        ctx.add_user_message(f"turn {i}")
        ctx.add_assistant_message(f"reply {i}")

    assert len(ctx.history) <= 4


def test_intent_router_classification():
    router = IntentRouter()

    # Memory Store
    res_store = router.classify("remember that mission is Project Veronica")
    assert res_store.intent == IntentType.MEMORY_STORE
    assert res_store.params.get("key") == "mission"
    assert res_store.params.get("value") == "Project Veronica"

    # Memory Query
    res_query = router.classify("what is my mission")
    assert res_query.intent == IntentType.MEMORY_QUERY
    assert res_query.params.get("key") == "mission"

    # Telemetry
    res_telem = router.classify("check hardware vitals and cpu")
    assert res_telem.intent == IntentType.TELEMETRY

    # Workspace Macro
    res_macro = router.classify("deploy dev mode")
    assert res_macro.intent == IntentType.WORKSPACE_MACRO
    assert res_macro.params.get("mode") == "dev"

    # Directive Action
    res_action = router.classify("open spotify and play music")
    assert res_action.intent == IntentType.DIRECTIVE_ACTION


def test_tool_schemas_and_dispatcher():
    assert len(TOOL_SCHEMAS) >= 5
    schema_names = [s["function"]["name"] for s in TOOL_SCHEMAS]
    assert "get_system_telemetry" in schema_names
    assert "launch_application" in schema_names
    assert "media_control" in schema_names

    # Test dispatch
    telem = dispatch_tool_call("get_system_telemetry", {})
    assert "cpu_percent" in telem
    assert "ram_percent" in telem

    mem_res = dispatch_tool_call("memory_store", {"action": "set", "key": "agent", "value": "Veronica"})
    assert mem_res.get("status") == "success"


@pytest.mark.asyncio
async def test_intelligence_engine_streaming_and_status():
    engine = IntelligenceEngine()
    status = engine.get_engine_status()
    assert "active_provider" in status
    assert len(status["providers"]) >= 5

    # Test conversational streaming with TacticalCore
    chunks = []
    async for chunk in engine.stream_reply("Hello Veronica"):
        chunks.append(chunk)
    reply = "".join(chunks)
    assert len(reply) > 5

    # Test memory store intent streaming
    store_chunks = []
    async for chunk in engine.stream_reply("remember that suit is Mark 85"):
        store_chunks.append(chunk)
    store_reply = "".join(store_chunks)
    assert "committed" in store_reply.lower() or "tactical memory" in store_reply.lower()

    # Test memory recall query streaming
    query_chunks = []
    async for chunk in engine.stream_reply("what is my suit"):
        query_chunks.append(chunk)
    query_reply = "".join(query_chunks)
    assert "mark 85" in query_reply.lower()
