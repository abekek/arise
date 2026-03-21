"""Optional OpenTelemetry integration for ARISE evolution tracing.

When opentelemetry is installed and config.enable_telemetry is True, evolution
steps are wrapped with OTel spans. Otherwise, all functions are safe no-ops.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

_tracer = None

try:
    from opentelemetry import trace

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


def _get_tracer():
    global _tracer
    if _tracer is None and _HAS_OTEL:
        _tracer = trace.get_tracer("arise")
    return _tracer


@contextmanager
def start_evolution_span(
    name: str, enabled: bool = True
) -> Generator[Any, None, None]:
    """Start a span for an evolution step. Yields the span (or None)."""
    if not enabled or not _HAS_OTEL:
        yield None
        return

    tracer = _get_tracer()
    with tracer.start_as_current_span(name) as span:
        yield span


def add_span_attribute(span: Any, key: str, value: Any) -> None:
    """Add an attribute to a span if it exists."""
    if span is None or not _HAS_OTEL:
        return
    span.set_attribute(key, value)


def end_span(span: Any) -> None:
    """End a span explicitly. Usually not needed with context manager."""
    if span is None or not _HAS_OTEL:
        return
    # Spans are ended automatically by the context manager; this is a
    # convenience for manual span management if needed.


def is_available() -> bool:
    """Return True if OpenTelemetry is installed."""
    return _HAS_OTEL
