"""TraceBoard SDK — tracing adapters for multiple LLM frameworks."""

from traceboard.sdk._base import BaseTracer
from traceboard.sdk.exporter import TraceExporter
from traceboard.sdk.processor import TraceBoardProcessor

__all__ = [
    "BaseTracer",
    "TraceBoardProcessor",
    "TraceExporter",
]

# Lazy imports for optional adapters — avoids ImportError when
# anthropic / langchain / litellm are not installed.


def __getattr__(name: str):
    if name == "AnthropicTracer":
        from traceboard.sdk.anthropic_tracer import AnthropicTracer
        return AnthropicTracer
    if name == "TraceBoardCallbackHandler":
        from traceboard.sdk.langchain_handler import TraceBoardCallbackHandler
        return TraceBoardCallbackHandler
    if name == "TraceBoardLiteLLMLogger":
        from traceboard.sdk.litellm_logger import TraceBoardLiteLLMLogger
        return TraceBoardLiteLLMLogger
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
