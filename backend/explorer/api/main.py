"""FastAPI application.

Issue #1 scope: the stack boots and /healthz reports on each dependency independently.
Routes for the product land in later issues; this is the floor everything else stands on.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from explorer import __version__
from explorer.api.admin import router as admin_router
from explorer.api.agent import router as agent_router
from explorer.api.catalog import router as catalog_router
from explorer.api.comparables import router as comparables_router
from explorer.api.coverage import router as coverage_router
from explorer.api.deal_terms import router as deal_terms_router
from explorer.api.errors import install_error_handlers
from explorer.api.facets import router as facets_router
from explorer.api.grading import router as grading_router
from explorer.api.label import router as label_router
from explorer.api.logging import bind_request, clear_request, configure_logging, get_logger
from explorer.api.matters import router as matters_router
from explorer.api.run_selection import router as run_selection_router
from explorer.api.settings import settings
from explorer.api.tables import router as tables_router

configure_logging(settings.log_level)
log = get_logger()

app = FastAPI(
    title="Clause Explorer",
    version=__version__,
    description=(
        "Comparable-deals workbench. Find deals like the one in front of you, see what "
        "was negotiated across them, and know where experience is thin."
    ),
)

install_error_handlers(app)
app.include_router(comparables_router)
app.include_router(facets_router)
app.include_router(matters_router)
app.include_router(deal_terms_router)
app.include_router(coverage_router)
app.include_router(admin_router)
app.include_router(label_router)
app.include_router(tables_router)
app.include_router(agent_router)
app.include_router(catalog_router)
app.include_router(run_selection_router)
app.include_router(grading_router)

_STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Bind a request id, log start and end with timing, echo it back as a header.

    The id is bound to contextvars rather than passed around, so anything logged deeper
    in the call stack inherits it without changing signatures.
    """
    rid = bind_request(request.headers.get("x-request-id"))
    started = time.perf_counter()
    log.info("request_start", method=request.method, path=request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        log.exception(
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        clear_request()
        raise
    log.info(
        "request_end",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    response.headers["x-request-id"] = rid
    clear_request()
    return response


class Health(BaseModel):
    """Per-dependency health.

    Deliberately not a single boolean: the only useful thing this endpoint can tell an
    operator is *which* dependency is down.
    """

    status: str  # "ok" when every dependency is reachable, else "degraded"
    db: str  # "ok" | "unreachable"
    cube: str  # "ok" | "unreachable"
    version: str


def _check_db() -> str:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return "ok"
    except Exception:  # noqa: BLE001 - a health check must never propagate; any failure means unreachable
        # The exception is deliberately not surfaced: the DSN carries credentials and
        # this endpoint is unauthenticated.
        return "unreachable"


def _check_cube() -> str:
    try:
        resp = httpx.get(f"{settings.cube_api_url}/meta", timeout=2.0)
        return "ok" if resp.status_code < 500 else "unreachable"
    except Exception:  # noqa: BLE001 - same rationale as _check_db
        return "unreachable"


@app.get("/healthz", response_model=Health)
def healthz() -> Health:
    """Report each dependency separately; status is ok only if all are reachable."""
    db, cube = _check_db(), _check_cube()
    return Health(
        status="ok" if db == "ok" and cube == "ok" else "degraded",
        db=db,
        cube=cube,
        version=__version__,
    )


# response_model=None: the return is a union of Response subclasses, which FastAPI
# cannot turn into a Pydantic response model.
@app.get("/", response_class=HTMLResponse, response_model=None)
def root() -> HTMLResponse | FileResponse:
    """Serve the built frontend when present.

    In compose, nginx serves the SPA and proxies /api here, so this path is only hit in
    local dev before a frontend build exists. Returning a usable pointer beats a 404.
    """
    index = _STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>Clause Explorer</title>"
        "<body style='font:14px ui-monospace,monospace;background:#010102;color:#f7f8f8;"
        "padding:2rem'><h1 style='color:#5e6ad2;font-size:1rem'>clause explorer</h1>"
        "<p>API is up. The frontend is not built yet.</p>"
        "<p><a style='color:#5e6ad2' href='/docs'>/docs</a> &middot; "
        "<a style='color:#5e6ad2' href='/healthz'>/healthz</a></p></body>"
    )
