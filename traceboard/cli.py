"""TraceBoard CLI — command-line interface.

Usage:
    traceboard ui              Start the web dashboard
    traceboard ui --port 9000  Custom port
    traceboard clean           Delete all trace data
    traceboard export          Export traces to JSON (default) or CSV
"""

from __future__ import annotations

import json
import sys
import asyncio
from pathlib import Path

import click


@click.group()
@click.version_option(version="0.1.1", prog_name="traceboard")
def main():
    """TraceBoard — Local-first AI Agent observability & debugging toolkit."""
    pass


@main.command()
@click.option("--port", "-p", default=8745, help="Port to serve on (default: 8745)")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
@click.option("--db", default="./traceboard.db", help="Path to SQLite database (default: ./traceboard.db)")
@click.option("--no-open", is_flag=True, help="Don't auto-open the browser")
def ui(port: int, host: str, db: str, no_open: bool):
    """Start the TraceBoard web dashboard."""
    import uvicorn
    from traceboard.server.app import create_app

    db_path = str(Path(db).resolve())
    app = create_app(db_path=db_path)

    click.echo(f"")
    click.echo(f"  TraceBoard v0.1.1")
    click.echo(f"  Dashboard: http://{host}:{port}")
    click.echo(f"  Database:  {db_path}")
    click.echo(f"")

    if not no_open:
        import webbrowser
        import threading

        def open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


@main.command()
@click.option("--db", default="./traceboard.db", help="Path to SQLite database")
@click.confirmation_option(prompt="This will delete ALL trace data. Continue?")
def clean(db: str):
    """Delete all trace data."""
    db_path = str(Path(db).resolve())

    if not Path(db_path).exists():
        click.echo(f"No database found at {db_path}")
        return

    async def _clean():
        from traceboard.server.database import Database
        database = Database(db_path=db_path)
        await database.connect()
        count = await database.delete_all()
        await database.close()
        return count

    count = asyncio.run(_clean())
    click.echo(f"Deleted {count} traces from {db_path}")


@main.command()
@click.option("--db", default="./traceboard.db", help="Path to SQLite database")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout for JSON)")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "csv"]), default="json", help="Export format (default: json)")
@click.option("--pretty", is_flag=True, help="Pretty-print JSON output")
def export(db: str, output: str | None, fmt: str, pretty: bool):
    """Export all traces to JSON or CSV."""
    db_path = str(Path(db).resolve())

    if not Path(db_path).exists():
        click.echo(f"No database found at {db_path}", err=True)
        sys.exit(1)

    from traceboard.sdk.exporter import TraceExporter

    exporter = TraceExporter(db_path=db_path)

    if fmt == "csv":
        if not output:
            output = "traceboard_export.csv"
        exporter.export_csv(output)
        click.echo(f"Exported traces to {output}")
        spans_path = Path(output).with_name(f"{Path(output).stem}_spans.csv")
        if spans_path.exists():
            click.echo(f"Exported spans  to {spans_path}")
    else:
        data = exporter.export_json(output, pretty=pretty or (output is not None))
        if output:
            count = data.get("trace_count", 0)
            click.echo(f"Exported {count} traces to {output}")
        else:
            indent = 2 if pretty else None
            click.echo(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
