"""Uniform error envelope.

Every non-2xx response has the same shape so the frontend has one error path instead of
three: FastAPI's default `detail` string, its validation array, and whatever an unhandled
exception renders as.

    {"error": {"code": "...", "message": "...", "detail": ...}}

Internal errors deliberately return a generic message. A traceback can carry the DSN or an
API key, and these endpoints are unauthenticated.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from explorer.api.logging import get_logger

log = get_logger()

_CODES: dict[int, str] = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    503: "unavailable",
}


def envelope(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODES.get(exc.status_code, f"http_{exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(code, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Surface which field failed — a bare "validation error" is unactionable.
        detail = [
            {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]} for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=envelope("validation_error", "request failed validation", detail),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the real cause with the request id; return nothing specific to the caller.
        log.exception("unhandled_exception", path=request.url.path, kind=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=envelope("internal_error", "an internal error occurred"),
        )


__all__ = ["HTTPException", "envelope", "install_error_handlers"]
