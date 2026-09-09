"""`POST /ask` — one question in, a governed answer and its whole derivation out.

The tab this serves used to be two steps: `/agent/ask` returned a selection, a person confirmed
it as chips, and `/agent/run-selection` computed the number. That gate is justified by this
domain's own measured weakness (0.50 filter exact-match), and it was also charged on every
question including the ones where nothing was guessed at all.

So the confirmation is now **conditional**, and the server decides because only the server knows
which rung of the resolution ladder each value came off:

* every value matched **exactly** — a case-insensitive comparison against the corpus's own
  distinct values, free, deterministic, no model call — and the question runs immediately.
* anything else is a **guess**, and a guess stops and asks, offering the values the corpus
  actually carries.

A `verbatim` value is treated as a guess unless it is checked and found. That is the correction
this route exists to make: deal-point names arrive as the model's own text, nothing compared them
to the 92 real ABA names, and *"do MAE definitions carve out pandemics"* returned a confident
answer about `Target "prospects"` — a fluent answer to a question nobody asked. Comparing the
name against the vocabulary costs one cached query and turns that class of failure into a prompt.

Everything that computes runs through `run_selection.execute`, unchanged, so the `min_n` gate and
the identifying-dimension refusal apply here exactly as they do everywhere else. This route adds
a receipt; it does not add a path.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from openai import RateLimitError
from pydantic import BaseModel, Field
from semantic_explorer_base.agent.receipt import Receipt
from semantic_explorer_base.agent.receipt import build as build_receipt

from explorer.agent.dimension_values import dimension_values
from explorer.agent.select import (
    AgentUnavailable,
    InvalidSelection,
    Vocabulary,
    fetch_vocabulary,
    validate_selection,
)
from explorer.api.ask import (
    _collapse,
    _interpret_or_fall_back,
    _refuse_a_stated_figure,
    _resolve_values,
    _usage,
)
from explorer.api.cube_client import meta as cube_meta
from explorer.api.cube_client import query as cube_query
from explorer.api.cube_client import sql as cube_sql
from explorer.api.logging import get_logger
from explorer.api.run_selection import execute
from explorer.api.settings import settings
from explorer.domain import DOMAIN

router = APIRouter()
log = get_logger()

#: Methods that mean "this value is the corpus's own, verified". Everything else is a guess.
VERIFIED = {"exact"}


class ConsoleFilter(BaseModel):
    member: str
    operator: str = "equals"
    values: list[str] = Field(default_factory=list)


class ConsoleSelection(BaseModel):
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[ConsoleFilter] = Field(default_factory=list)


class AskConsoleRequest(BaseModel):
    question: str
    #: A selection the reader reviewed. Present only on the second call of a confirmed guess;
    #: it skips interpretation entirely, so confirming costs no model call.
    confirmed: ConsoleSelection | None = None


class ConsoleResolution(BaseModel):
    raw: str
    resolved: str
    method: str
    #: What the corpus carries, offered when this value was guessed.
    candidates: list[str] = Field(default_factory=list)


class AskConsoleResponse(BaseModel):
    question: str
    resolved_query: str
    selection: dict[str, Any]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    n: int | None = None
    refused: bool = False
    threshold: int | None = None
    message: str | None = None
    declined: bool = False
    decline_reason: str | None = None
    receipt: Receipt | None = None
    records: list[dict[str, Any]] | None = None
    needs_confirmation: bool = False
    resolutions: list[ConsoleResolution] = Field(default_factory=list)
    #: What this question cost. Reported rather than estimated, so the tab can show a running
    #: session total — a claim about cost nobody can check is worth nothing.
    usage: dict[str, Any] | None = None


def _verify(member: str, resolved: str, method: str) -> tuple[str, list[str]]:
    """Re-check one resolved value against what the dimension actually carries.

    Returns the method to report and the candidate list to offer. A value found in the
    vocabulary is `exact` however it was arrived at — the ladder's rung stops mattering once
    the answer is confirmed to exist. A value NOT found keeps its rung and drags the whole
    question into confirmation, which is the honest outcome: nobody checked it.
    """
    values = dimension_values(member)
    if not values:
        # No closed vocabulary to check against — a date, a free-text name. Verbatim travel is
        # correct here and refusing it would make the resolver a censor.
        return method, []
    if any(v.lower() == resolved.lower() for v in values):
        return "exact", []
    return method, list(values)[:200]


def _resolved_query(selection: dict[str, Any], n: int | None) -> str:
    """The one-line restatement above every answer, so a domain expert can catch a misreading
    without opening the receipt."""
    parts: list[str] = []
    for f in selection.get("filters", []):
        member = str(f.get("member", "")).split(".")[-1]
        parts.append(f"{member}={', '.join(f.get('values') or [])}")
    for d in selection.get("dimensions", []):
        parts.append(f"by {d.split('.')[-1]}")
    head = DOMAIN.strings.get("records", "records") if DOMAIN.strings else "records"
    line = f"{head} where {' , '.join(parts)}" if parts else f"all {head}"
    return f"{line} · n={n}" if n is not None else line


@router.post("/ask", response_model=AskConsoleResponse)
def ask_console(request: AskConsoleRequest) -> AskConsoleResponse:
    try:
        vocabulary: Vocabulary = fetch_vocabulary()
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if request.confirmed is None and not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY is not set, so a question cannot be turned into a selection. "
                "Set it in .env and restart the API."
            ),
        )

    resolutions: list[ConsoleResolution] = []
    usage: dict[str, Any] | None = None

    if request.confirmed is not None:
        selection: dict[str, Any] = {
            "measures": request.confirmed.measures,
            "dimensions": request.confirmed.dimensions,
            "filters": [f.model_dump() for f in request.confirmed.filters],
        }
    else:
        started = time.perf_counter()
        token_usage: list[tuple[int, int]] = []
        try:
            selection, _call = _interpret_or_fall_back(
                request.question, vocabulary, token_usage, started
            )
        except RateLimitError as limited:
            log.warning("ask_console_rate_limited", detail=str(limited)[:200])
            raise HTTPException(
                status_code=503,
                detail=(
                    "The model provider returned a rate limit, so this question was not "
                    "interpreted. Nothing is wrong with the corpus or the query — the same "
                    "question will work once the limit resets."
                ),
            ) from limited

        usage = _usage(_call).model_dump()
        _refuse_a_stated_figure(selection)
        selection["measures"] = _collapse(list(selection.get("measures", [])))
        selection["dimensions"] = _collapse(list(selection.get("dimensions", [])))

        resolved_filters: list[dict[str, Any]] = []
        for f in selection.get("filters", []):
            values, raw_resolutions, _blockers = _resolve_values(
                f["member"], list(f.get("values", [])), vocabulary
            )
            for r in raw_resolutions:
                method, candidates = _verify(f["member"], r.resolved or r.raw, r.method)
                resolutions.append(
                    ConsoleResolution(
                        raw=r.raw,
                        resolved=r.resolved or r.raw,
                        method=method,
                        candidates=candidates,
                    )
                )
            resolved_filters.append(
                {"member": f["member"], "operator": f.get("operator", "equals"), "values": values}
            )
        selection["filters"] = resolved_filters

    try:
        # The domain's wrapper already binds DOMAIN, which is what carries the
        # identifying-dimension refusal.
        validate_selection(selection, vocabulary)
    except InvalidSelection as invalid:
        log.warning("ask_console_rejected", reason=str(invalid))
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid

    guessed = [r for r in resolutions if r.method not in VERIFIED]
    if guessed:
        # Nothing has run. The selection travels back so confirming costs no second model call.
        log.info("ask_console_needs_confirmation", guesses=[g.raw for g in guessed])
        return AskConsoleResponse(
            question=request.question,
            resolved_query=_resolved_query(selection, None),
            selection=selection,
            needs_confirmation=True,
            resolutions=resolutions,
            usage=usage,
        )

    _rows, gate = execute(selection, limit=200)
    receipt = build_receipt(
        selection,
        tuple(resolutions),
        domain=DOMAIN,
        sql=cube_sql,
        meta=cube_meta,
        query=cube_query,
    )
    log.info(
        "ask_console",
        refused=gate.refused,
        n=gate.n,
        rows=len(gate.rows),
        receipt=receipt is not None,
    )
    return AskConsoleResponse(
        question=request.question,
        resolved_query=_resolved_query(selection, gate.n),
        selection=selection,
        rows=gate.rows,
        n=gate.n,
        refused=gate.refused,
        threshold=gate.threshold,
        message=gate.message,
        receipt=receipt,
        resolutions=resolutions,
        usage=usage,
    )
