"""
TraceBoard — Local-first AI Agent observability & debugging toolkit.

Usage:
    import traceboard
    traceboard.init()
"""

from traceboard.config import TraceboardConfig
from traceboard.sdk.exporter import TraceExporter
from traceboard.sdk.processor import TraceBoardProcessor

__version__ = "0.1.0"
__all__ = ["init", "get_processor", "TraceboardConfig", "TraceExporter"]

_processor: TraceBoardProcessor | None = None


def init(
    db_path: str = "./traceboard.db",
    auto_open: bool = False,
) -> TraceBoardProcessor:
    """Initialize TraceBoard tracing.

    Registers a TraceBoardProcessor with the OpenAI Agents SDK
    so all agent runs are automatically traced to a local SQLite database.

    Args:
        db_path: Path to the SQLite database file. Defaults to ./traceboard.db.
        auto_open: If True, automatically open the web dashboard after init.

    Returns:
        The TraceBoardProcessor instance.
    """
    global _processor

    from agents.tracing import add_trace_processor

    config = TraceboardConfig(db_path=db_path)
    _processor = TraceBoardProcessor(config=config)
    add_trace_processor(_processor)

    if auto_open:
        import webbrowser
        webbrowser.open(f"http://localhost:8745")

    return _processor


def get_processor() -> TraceBoardProcessor | None:
    """Get the current TraceBoardProcessor instance, or None if not initialized."""
    return _processor
