"""Arize AX: every Claude call (auto-instrumented) plus one span per pipeline step."""

import contextlib
import json
from typing import Any, Iterator

from opentelemetry import trace

from billingrep import config

_provider = None


def setup() -> bool:
    global _provider
    if _provider is not None or not config.has("ARIZE_SPACE_ID", "ARIZE_API_KEY"):
        return _provider is not None
    import os

    from arize.otel import register
    from openinference.instrumentation.anthropic import AnthropicInstrumentor

    _provider = register(
        space_id=os.environ["ARIZE_SPACE_ID"], api_key=os.environ["ARIZE_API_KEY"], project_name=config.ARIZE_PROJECT
    )
    AnthropicInstrumentor().instrument(tracer_provider=_provider)
    return True


def tracer():
    return trace.get_tracer("billingrep")


@contextlib.contextmanager
def span(name: str, kind: str = "CHAIN", **attrs: Any) -> Iterator[Any]:
    with tracer().start_as_current_span(name) as s:
        s.set_attribute("openinference.span.kind", kind)
        for k, v in attrs.items():
            s.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else json.dumps(v, default=str))
        yield s


def trace_id(s: Any) -> str:
    ctx = s.get_span_context()
    return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else ""


def flush() -> None:
    if _provider is not None:
        with contextlib.suppress(Exception):
            _provider.force_flush(5000)
