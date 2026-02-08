"""TraceBoard configuration."""

from dataclasses import dataclass, field


@dataclass
class TraceboardConfig:
    """Configuration for TraceBoard."""

    db_path: str = "./traceboard.db"
    """Path to the SQLite database file."""

    server_host: str = "127.0.0.1"
    """Host to bind the web server to."""

    server_port: int = 8745
    """Port for the web server."""

    batch_size: int = 50
    """Number of items to batch before flushing to SQLite."""

    flush_interval: float = 2.0
    """Seconds between automatic flushes."""
