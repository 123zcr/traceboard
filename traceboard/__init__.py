"""
TraceBoard — Local-first AI Agent observability & debugging toolkit.

Usage::

    import traceboard

    # Auto-detect and instrument all installed SDKs
    traceboard.init()

    # Or specify which frameworks to instrument
    traceboard.init(frameworks=["openai", "anthropic", "langchain", "litellm"])
"""

from traceboard.config import TraceboardConfig
from traceboard.sdk.exporter import TraceExporter

__version__ = "0.2.0"
__all__ = [
    "init",
    "init_openai",
    "init_anthropic",
    "init_langchain",
    "init_litellm",
    "get_processor",
    "TraceboardConfig",
    "TraceExporter",
]

import logging

logger = logging.getLogger("traceboard")

# Global adapter instances
_openai_processor = None
_anthropic_tracer = None
_langchain_handler = None
_litellm_logger = None


def init(
    db_path: str = "./traceboard.db",
    auto_open: bool = False,
    frameworks: list[str] | None = None,
) -> dict[str, object]:
    """Initialize TraceBoard tracing.

    Auto-detects installed SDKs and instruments them so all LLM calls
    are traced to a local SQLite database.  Use ``frameworks`` to limit
    which SDKs are instrumented.

    Args:
        db_path: Path to the SQLite database file.
        auto_open: If True, automatically open the web dashboard.
        frameworks: List of frameworks to instrument.  Supported values:
            ``"openai"``, ``"anthropic"``, ``"langchain"``, ``"litellm"``.
            If None, auto-detects all installed SDKs.

    Returns:
        A dict mapping framework names to their adapter instances.
    """
    config = TraceboardConfig(db_path=db_path)
    adapters: dict[str, object] = {}

    # Determine which frameworks to try
    all_frameworks = ["openai", "anthropic", "langchain", "litellm"]
    targets = frameworks if frameworks is not None else all_frameworks

    for fw in targets:
        try:
            if fw == "openai":
                adapters["openai"] = _init_openai(config)
            elif fw == "anthropic":
                adapters["anthropic"] = _init_anthropic(config)
            elif fw == "langchain":
                adapters["langchain"] = _init_langchain(config)
            elif fw == "litellm":
                adapters["litellm"] = _init_litellm(config)
            else:
                logger.warning("TraceBoard: unknown framework %r", fw)
        except ImportError:
            if frameworks is not None:
                # User explicitly requested this framework — warn loudly
                logger.warning(
                    "TraceBoard: framework %r requested but not installed", fw
                )
            # If auto-detecting, silently skip missing SDKs

    if not adapters:
        logger.warning(
            "TraceBoard: no supported SDK found. Install one of: "
            "openai-agents, anthropic, langchain-core, litellm"
        )

    if auto_open:
        import webbrowser
        webbrowser.open("http://localhost:8745")

    logger.info("TraceBoard initialized — %s", ", ".join(adapters) or "no adapters")
    return adapters


# ── Individual init functions ──────────────────────────────────────────


def init_openai(db_path: str = "./traceboard.db") -> object:
    """Initialize tracing for OpenAI Agents SDK only."""
    return _init_openai(TraceboardConfig(db_path=db_path))


def init_anthropic(db_path: str = "./traceboard.db") -> object:
    """Initialize tracing for Anthropic SDK only.

    Returns an ``AnthropicTracer`` instance.  Use its ``.instrument()``
    method to wrap an existing client, or call it without arguments to
    create a new instrumented ``Anthropic()`` client.
    """
    return _init_anthropic(TraceboardConfig(db_path=db_path))


def init_langchain(db_path: str = "./traceboard.db") -> object:
    """Initialize tracing for LangChain.

    Returns a ``TraceBoardCallbackHandler`` instance.  Pass it to
    LangChain via the ``callbacks`` parameter.
    """
    return _init_langchain(TraceboardConfig(db_path=db_path))


def init_litellm(db_path: str = "./traceboard.db") -> object:
    """Initialize tracing for LiteLLM.

    Automatically registers a callback logger with ``litellm.callbacks``.
    """
    return _init_litellm(TraceboardConfig(db_path=db_path))


# ── Internal init helpers ──────────────────────────────────────────────


def _init_openai(config: TraceboardConfig) -> object:
    global _openai_processor
    from agents.tracing import add_trace_processor
    from traceboard.sdk.processor import TraceBoardProcessor

    _openai_processor = TraceBoardProcessor(config=config)
    add_trace_processor(_openai_processor)
    logger.info("TraceBoard: OpenAI Agents SDK instrumented")
    return _openai_processor


def _init_anthropic(config: TraceboardConfig) -> object:
    global _anthropic_tracer
    import anthropic  # noqa: F401 — verify installed

    from traceboard.sdk.anthropic_tracer import AnthropicTracer

    _anthropic_tracer = AnthropicTracer(config=config)
    logger.info(
        "TraceBoard: Anthropic SDK ready — use tracer.instrument() to wrap clients"
    )
    return _anthropic_tracer


def _init_langchain(config: TraceboardConfig) -> object:
    global _langchain_handler
    import langchain_core  # noqa: F401

    from traceboard.sdk.langchain_handler import TraceBoardCallbackHandler

    _langchain_handler = TraceBoardCallbackHandler(config=config)
    logger.info(
        "TraceBoard: LangChain handler ready — pass to callbacks=[] parameter"
    )
    return _langchain_handler


def _init_litellm(config: TraceboardConfig) -> object:
    global _litellm_logger
    import litellm

    from traceboard.sdk.litellm_logger import TraceBoardLiteLLMLogger

    _litellm_logger = TraceBoardLiteLLMLogger(config=config)
    if not isinstance(litellm.callbacks, list):
        litellm.callbacks = []
    litellm.callbacks.append(_litellm_logger)
    logger.info("TraceBoard: LiteLLM logger registered")
    return _litellm_logger


# ── Accessor ───────────────────────────────────────────────────────────


def get_processor():
    """Get the OpenAI Agents SDK processor, or None."""
    return _openai_processor
