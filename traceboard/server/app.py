"""TraceBoard FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from traceboard.server.database import Database
from traceboard.server.routes.metrics import router as metrics_router
from traceboard.server.routes.spans import router as spans_router
from traceboard.server.routes.traces import router as traces_router


def create_app(db_path: str = "./traceboard.db") -> FastAPI:
    """Create and configure the FastAPI application."""

    db = Database(db_path=db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        yield
        await db.close()

    app = FastAPI(
        title="TraceBoard",
        description="Local-first AI Agent observability & debugging toolkit",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store db instance for route access
    app.state.db = db

    # CORS — allow local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(traces_router, prefix="/api")
    app.include_router(spans_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")

    # Serve dashboard static files
    dashboard_dir = Path(__file__).parent.parent / "dashboard"
    if dashboard_dir.exists():
        app.mount("/", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

    return app
