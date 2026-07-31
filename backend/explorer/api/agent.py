"""`POST /agent/select` (#24) and `POST /agent/resolve-filter-value` (#25).

Both are the agent's only two ways to touch the semantic layer: choose *what* to ask (a
Cube selection, enum-constrained) and resolve *which value* a free-text filter means. Neither
endpoint returns a number computed by the model — `/agent/select` executes the validated
selection through the same `cube_client.query()` every other endpoint uses, and
`/agent/resolve-filter-value` returns a label and a count read from Postgres/Cube, never text
the model asserted.
"""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.agent.resolve_filter_value import UnresolvedFilterValue, resolve_filter_value
from explorer.agent.select import (
    AgentUnavailable,
    InvalidSelection,
    fetch_vocabulary,
    select_via_llm,
    validate_selection,
)
from explorer.api.cube_client import CubeUnavailable
from explorer.api.cube_client import query as cube_query
from explorer.api.logging import get_logger
from explorer.api.settings import settings
from explorer.retrieval.embeddings import EmbeddingCache

router = APIRouter(prefix="/agent")
log = get_logger()


class SelectRequest(BaseModel):
    question: str = Field(min_length=1)


class SelectResponse(BaseModel):
    selection: dict[str, Any] = Field(
        description="What the model chose — never itself a number. Shown above the answer so "
        "a domain expert can catch a misinterpretation (#26)."
    )
    rows: list[dict[str, Any]] = Field(
        description="Computed by Cube from the validated selection. This, not the model, is "
        "where every number in the response comes from."
    )


@router.post("/select", response_model=SelectResponse)
def select(request: SelectRequest) -> SelectResponse:
    if not settings.has_openai_key:
        raise HTTPException(
            status_code=503,
            detail="The agent needs OPENAI_API_KEY. Facets, comparables, deal terms and "
            "coverage all work without one; this endpoint alone requires it.",
        )

    try:
        vocabulary = fetch_vocabulary()
    except AgentUnavailable as unavailable:
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    selection = select_via_llm(request.question, vocabulary, settings.openai_api_key)  # type: ignore[arg-type]

    try:
        validate_selection(selection, vocabulary)
    except InvalidSelection as invalid:
        log.warning("agent_selection_rejected", selection=selection, reason=str(invalid))
        raise HTTPException(status_code=400, detail=str(invalid)) from invalid

    try:
        rows = cube_query(
            {
                "measures": selection.get("measures", []),
                "dimensions": selection.get("dimensions", []),
                "filters": selection.get("filters", []),
                "timeDimensions": selection.get("timeDimensions", []),
            }
        )
    except CubeUnavailable as unavailable:
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    log.info("agent_selection_executed", selection=selection, row_count=len(rows))
    return SelectResponse(selection=selection, rows=rows)


class ResolveValueRequest(BaseModel):
    value: str = Field(min_length=1)


class ResolveValueResponse(BaseModel):
    raw: str
    resolved: str
    method: str
    matter_count: int
    similarity: float | None = None


@router.post("/resolve-filter-value", response_model=ResolveValueResponse)
def resolve_value(request: ResolveValueRequest) -> ResolveValueResponse:
    with psycopg.connect(settings.database_url) as conn:
        cache = EmbeddingCache(api_key=settings.openai_api_key)
        try:
            result = resolve_filter_value(conn, cache, request.value)
        except UnresolvedFilterValue as unresolved:
            # Loud, not empty: a 422 naming the candidates, never a silent [] that reads
            # identically to "the corpus has no comparable deals" (#25's central failure mode).
            raise HTTPException(
                status_code=422,
                detail={"message": str(unresolved), "candidates": unresolved.candidates},
            ) from unresolved

    return ResolveValueResponse(
        raw=result.raw,
        resolved=result.resolved,
        method=result.method,
        matter_count=result.matter_count,
        similarity=result.similarity,
    )
