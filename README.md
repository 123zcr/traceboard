**English** | [中文](README_zh.md) | [日本語](README_ja.md)

# TraceBoard

**Local-first AI Agent observability & debugging toolkit.**

TraceBoard is the *SQLite of Agent tracing* — zero config, fully local, instant setup. No cloud accounts, no Docker, no external databases. Just `pip install` and go.

---

## Features

- **Zero Config** — `pip install traceboard` + 2 lines of code
- **Local First** — All data stored in a local SQLite file, zero privacy risk
- **Built-in Web Dashboard** — `traceboard ui` opens an interactive trace viewer
- **OpenAI Agents SDK** — Native integration via `TracingProcessor` interface
- **Cost Tracking** — Automatic per-model cost calculation (GPT-4o, o1, o3, GPT-4.1, etc.)
- **Live Updates** — WebSocket-powered real-time view with HTTP polling fallback
- **Data Export** — Export traces to JSON or CSV for offline analysis
- **Offline** — Works without any internet connection

## Quick Start

### Install

```bash
pip install traceboard
```

### Integrate (2 lines)

```python
import traceboard
traceboard.init()

# Your existing OpenAI Agents SDK code — no changes needed
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="You are a helpful assistant.")
result = Runner.run_sync(agent, "Hello!")
print(result.final_output)
```

### View Traces

```bash
traceboard ui
```

This opens a local web dashboard at `http://localhost:8745` where you can:

- Browse all traced agent runs
- Visualize execution timelines (Gantt-chart style)
- Inspect LLM prompts/responses, tool calls, and handoffs
- Track token usage and costs per model
- View aggregated metrics in real-time

## How It Works

```
┌────────────────────┐       ┌───────────────┐       ┌──────────────────┐
│  Your Agent Code   │       │   SQLite DB   │       │  Web Dashboard   │
│                    │       │               │       │                  │
│  traceboard.init() │──────>│ traceboard.db │<──────│  traceboard ui   │
│  Agent.run(...)    │ write │               │  read │  localhost:8745  │
└────────────────────┘       └───────────────┘       └──────────────────┘
```

TraceBoard implements the OpenAI Agents SDK's `TracingProcessor` interface. When you call `traceboard.init()`, it registers a custom processor that captures all traces and spans (LLM calls, tool calls, handoffs, guardrails) and writes them to a local SQLite database.

The web dashboard reads from this same SQLite file and presents the data through an interactive UI. When a WebSocket connection is available, the dashboard receives near-real-time updates (~1 s latency); otherwise it falls back to HTTP polling.

## CLI Commands

```bash
traceboard ui                        # Start web dashboard (default: http://localhost:8745)
traceboard ui --port 9000            # Custom port
traceboard ui --no-open              # Don't auto-open browser

traceboard export                    # Export all traces to JSON (stdout)
traceboard export -o traces.json     # Export to file
traceboard export -f csv -o data.csv # Export to CSV (traces + spans files)
traceboard export --pretty           # Pretty-print JSON

traceboard clean                     # Delete all trace data
```

## Configuration

```python
import traceboard

traceboard.init(
    db_path="./my_traces.db",   # Custom database path (default: ./traceboard.db)
    auto_open=False,             # Don't auto-open browser on init
)
```

## Programmatic Export

```python
from traceboard import TraceExporter

exporter = TraceExporter("./traceboard.db")

# Export all traces to JSON file
data = exporter.export_json("traces.json")

# Export specific traces to CSV
exporter.export_csv("output.csv", trace_ids=["trace_abc123"])

# Get data in memory (no file written)
data = exporter.export_json()
print(f"Exported {data['trace_count']} traces")
```

## Supported Models (Cost Tracking)

TraceBoard automatically calculates costs for **80+ model variants** based on [OpenAI's official pricing](https://platform.openai.com/docs/pricing):

| Model Family | Models |
|---|---|
| GPT-5.2 | `gpt-5.2`, `gpt-5.2-pro`, `gpt-5.2-codex` |
| GPT-5.1 | `gpt-5.1`, `gpt-5.1-codex`, `gpt-5.1-codex-max`, `gpt-5.1-codex-mini` |
| GPT-5 | `gpt-5`, `gpt-5-pro`, `gpt-5-mini`, `gpt-5-nano` |
| GPT-4.1 | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano` |
| GPT-4o | `gpt-4o`, `gpt-4o-mini` |
| o-series | `o1`, `o1-pro`, `o1-mini`, `o3`, `o3-pro`, `o3-mini`, `o4-mini` |
| Realtime | `gpt-realtime`, `gpt-realtime-mini` |
| Codex | `codex-mini-latest` |
| Legacy | `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo` |

Unknown models fall back to default pricing ($2.00/$8.00 per 1M tokens). Pricing data is sourced from OpenAI's official pricing page and updated with each release.

## Architecture

```
traceboard/
├── __init__.py          # Public API: init(), get_processor()
├── cli.py               # CLI commands (ui, clean, export)
├── config.py            # Configuration dataclass
├── cost.py              # Model pricing & cost calculation
├── sdk/
│   ├── processor.py     # TracingProcessor implementation
│   └── exporter.py      # JSON & CSV export utilities
├── server/
│   ├── app.py           # FastAPI application factory
│   ├── database.py      # Async + sync SQLite wrappers
│   ├── models.py        # Pydantic data models
│   └── routes/
│       ├── traces.py    # Trace CRUD endpoints
│       ├── spans.py     # Span query endpoints
│       └── metrics.py   # Metrics + WebSocket live updates
└── dashboard/
    ├── index.html       # Single-page dashboard (Alpine.js + Tailwind)
    └── static/
        ├── app.js       # Dashboard application logic
        └── styles.css   # Custom styles
```

## REST API

When the dashboard is running (`traceboard ui`), the following API endpoints are available:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/traces` | List traces (paginated, filterable) |
| `GET` | `/api/traces/{id}` | Get trace detail with all spans |
| `GET` | `/api/traces/{id}/spans` | Get flat span list for a trace |
| `GET` | `/api/traces/{id}/tree` | Get span tree for timeline view |
| `GET` | `/api/traces/{id}/export` | Export a single trace |
| `DELETE` | `/api/traces` | Delete all traces |
| `GET` | `/api/metrics` | Aggregated metrics |
| `GET` | `/api/export` | Export all data as JSON |
| `WS` | `/api/ws/live` | WebSocket for live metric updates |

## Development

```bash
# Clone and install in dev mode
git clone https://github.com/123zcr/traceboard.git
cd traceboard
pip install -e ".[dev]"

# Run tests
pytest

# Start dashboard in dev mode
traceboard ui --no-open
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes and add tests
4. Run `pytest` to ensure all tests pass
5. Submit a pull request

## Requirements

- Python >= 3.10
- OpenAI Agents SDK (`openai-agents`)

## License

[MIT](LICENSE)
