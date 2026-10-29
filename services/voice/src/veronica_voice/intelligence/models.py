"""Data models and type definitions for the Veronica Intelligence Backend Engine."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CircuitState(str, Enum):
    CLOSED = "closed"        # Operating normally; calls go through
    OPEN = "open"            # Failing repeatedly; short-circuiting calls
    HALF_OPEN = "half_open"  # Testing recovery with single probe


class IntentType(str, Enum):
    DIRECTIVE_ACTION = "directive_action"
    TELEMETRY = "telemetry"
    MEMORY_STORE = "memory_store"
    MEMORY_QUERY = "memory_query"
    MEMORY_LIST = "memory_list"
    VISION_INSPECT = "vision_inspect"
    WEB_SEARCH = "web_search"
    WORKSPACE_MACRO = "workspace_macro"
    CONVERSATION = "conversation"


@dataclass
class ModelMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class StreamChunk:
    text: str
    is_done: bool = False
    finish_reason: Optional[str] = None
    ttft_ms: Optional[float] = None


@dataclass
class AdapterMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    last_ttft_ms: float = 0.0
    avg_ttft_ms: float = 0.0
    total_tokens_estimated: int = 0

    def record_success(self, ttft_ms: float, tokens_count: int = 0) -> None:
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_success_time = time.time()
        self.last_ttft_ms = ttft_ms
        if self.avg_ttft_ms <= 0:
            self.avg_ttft_ms = ttft_ms
        else:
            self.avg_ttft_ms = (self.avg_ttft_ms * 0.8) + (ttft_ms * 0.2)
        self.total_tokens_estimated += tokens_count

    def record_failure(self) -> None:
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "consecutive_failures": self.consecutive_failures,
            "avg_ttft_ms": round(self.avg_ttft_ms, 1),
            "last_ttft_ms": round(self.last_ttft_ms, 1),
            "total_tokens_estimated": self.total_tokens_estimated,
        }


@dataclass
class IntentAnalysis:
    intent: IntentType
    confidence: float
    raw_query: str
    target_tools: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    fast_path_allowed: bool = True
