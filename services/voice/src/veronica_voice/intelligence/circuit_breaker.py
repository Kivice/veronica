"""Circuit Breaker pattern for AI provider resilience and zero-latency failover."""
from __future__ import annotations

import logging
import time
from typing import Optional

from .models import AdapterMetrics, CircuitState

logger = logging.getLogger("veronica.intelligence.circuit_breaker")


class CircuitBreaker:
    """Manages availability states and failure thresholds for external model endpoints."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.state = CircuitState.CLOSED
        self.metrics = AdapterMetrics()
        self._last_state_change: float = time.time()

    def can_execute(self) -> bool:
        """Check if calls to this provider should be attempted."""
        now = time.time()
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if now - self._last_state_change >= self.recovery_timeout_s:
                logger.info("CircuitBreaker[%s]: transitioning from OPEN to HALF_OPEN", self.name)
                self.state = CircuitState.HALF_OPEN
                self._last_state_change = now
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # In half-open, allow trial execution
            return True

        return False

    def record_success(self, ttft_ms: float = 0.0, tokens_count: int = 0) -> None:
        """Record successful execution. Closes circuit if in half-open state."""
        self.metrics.record_success(ttft_ms, tokens_count)
        if self.state != CircuitState.CLOSED:
            logger.info("CircuitBreaker[%s]: recovered, transitioning to CLOSED", self.name)
            self.state = CircuitState.CLOSED
            self._last_state_change = time.time()

    def record_failure(self) -> None:
        """Record failed execution. Trips circuit open if threshold exceeded."""
        self.metrics.record_failure()
        now = time.time()
        if self.state == CircuitState.CLOSED:
            if self.metrics.consecutive_failures >= self.failure_threshold:
                logger.warning(
                    "CircuitBreaker[%s]: failure threshold %d reached. Tripping to OPEN for %.1fs",
                    self.name,
                    self.failure_threshold,
                    self.recovery_timeout_s,
                )
                self.state = CircuitState.OPEN
                self._last_state_change = now
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning("CircuitBreaker[%s]: probe failed in HALF_OPEN. Re-opening circuit", self.name)
            self.state = CircuitState.OPEN
            self._last_state_change = now

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED with cleared failures."""
        self.state = CircuitState.CLOSED
        self.metrics.consecutive_failures = 0
        self._last_state_change = time.time()

    def status_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "metrics": self.metrics.to_dict(),
        }
