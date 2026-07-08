"""Lightweight per-request usage accounting.

Every Claude call in the pipeline reports its token usage here. The eval
harness (and later the API, if we want a cost header) resets the accumulator
before a run and reads it after, giving real measured token counts per claim
instead of estimates. Thread-local so concurrent requests don't mix numbers.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class UsageTotals:
    """Accumulated LLM usage for the current thread's request."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stage_calls: dict[str, int] = field(default_factory=dict)


_local = threading.local()


def _totals() -> UsageTotals:
    if not hasattr(_local, "totals"):
        _local.totals = UsageTotals()
    totals: UsageTotals = _local.totals
    return totals


def reset() -> None:
    """Zero the accumulator for a fresh request/eval item."""
    _local.totals = UsageTotals()


def record(stage: str, input_tokens: int, output_tokens: int) -> None:
    """Record one Claude call's usage against the current thread."""
    totals = _totals()
    totals.llm_calls += 1
    totals.input_tokens += input_tokens
    totals.output_tokens += output_tokens
    totals.stage_calls[stage] = totals.stage_calls.get(stage, 0) + 1


def snapshot() -> UsageTotals:
    """Return the current thread's accumulated usage."""
    return _totals()
