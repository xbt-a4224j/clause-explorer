"""`POST /agent/ask` (#47) — free text in, a *selection* out. Never an answer, never a number.

## Why this route exists

Before it, a user could exercise the whole product without a single live model call:
`select_via_llm` was reached only from the eval harness, the extractor only from calibration,
and the embedding cache is committed. The repo's central claim — that a model is constrained to
select from a governed vocabulary rather than to generate SQL — was asserted in prose and never
demonstrated on a path anyone could walk. A sceptical reader would have concluded this was a
faceted Postgres query tool with an eval bolted to the side, and they would have been right.

## The shape

Question -> `select_with_usage` (structured output, enum-constrained to Cube's live `/meta`) ->
validate -> resolve every filter value -> return chips. **Nothing executes here.** Cube's
`/load` is never touched on any path in this module; the user confirms or edits the chips and
the existing `POST /agent/run-selection` runs them, with its validation gate and `min_n`
refusal intact. That endpoint is where execution has always lived and this one does not
duplicate it.

`#45` deleted `POST /agent/select` because nothing called it. This is not a reversal of that:
what it lacked was a caller and a confirmation step, and both are what this adds.

## Why a human confirms the chips — measured, not stylistic

From `docs/eval/measure_selection.json`, graded by `evals/measure_selection.py` over 25 authored
cases:

    measure precision      0.80
    dimension precision    0.692
    filter exact-match     0.50
    refusal accuracy       0.20

Read as a shape rather than an average: the model is **decent at picking the measure**,
**mediocre at the filter value**, and **bad at knowing when to decline**. Each number lands on
a different part of this design. The measure is enum-locked, so its failures are visible in the
chip. The filter value cannot be enum-locked — it is free text describing corpus content — so
it goes down the resolution ladder below and fails loudly when it does not land. And refusal at
0.20 is why `min_n` is enforced in `run_selection.py` rather than requested in the system
prompt: a model this bad at declining cannot be the thing that decides whether a slice is too
thin to characterise.

The confirmation step is the mitigation for all three at once. It puts the interpretation in
front of the one person qualified to catch a misreading, before any figure is computed.

## The model emits no figure, and that is enforced rather than hoped for

`numeric_leaves()` walks the decoded model output and the route refuses anything carrying an
int or a float. The structured-output schema already makes numbers unrepresentable, so this
should never fire; it exists because "the schema will not let it" is a claim about a schema,
and this is a claim about the response that actually came back.
"""

from __future__ import annotations

import time
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from explorer.agent.interpret import interpret
from explorer.agent.pick_value import PICK_MODEL
from explorer.agent.resolve_filter_value import (
    UnresolvedFilterValue,
    resolve_filter_value,
)
from explorer.agent.select import (
    AgentUnavailable,
    InvalidSelection,
    SelectionCall,
    Vocabulary,
    fetch_vocabulary,
    select_with_usage,
    validate_selection,
)
from explorer.api.cube_client import query as cube_query  # noqa: F401 - see `no_cube` in tests
from explorer.api.logging import get_logger
from explorer.api.settings import settings
from explorer.evals.pricing import PRICE_CHECKED_ON, PRICE_SOURCE, cost_usd
from explorer.retrieval.embeddings import EmbeddingCache

router = APIRouter(prefix="/agent")
log = get_logger()

#: Filter members whose values are industry labels, and so are resolvable by the two-tier
#: ladder in `resolve_filter_value` (exact -> embedding nearest, #25/#49). Every other member
#: carries the model's text through marked `verbatim`: the ladder resolves against the
#: industry labels the corpus actually uses and has no vocabulary for a deal-point name or a
#: consideration type. Saying "verbatim" on the chip is honest; implying a resolution that
#: never ran is the failure this whole module is about.
RESOLVABLE_MEMBERS = frozenset({"comparable_deals.label", "industries.label"})

#: What Cube will accept as a value on a `boolean` dimension. Anything else can never match a
#: row. Measured on 2026-09-05: asked "how many aerospace deals do we have", the model filtered
#: `comparable_deals.has_industry = "Aerospace"`, and with that dimension removed from its
#: choices it moved to `is_inferred_industry = "Aerospace"` — it is matching the substring
#: "industry" in the name. Trimming the vocabulary chases that around; refusing a value the
#: dimension's own type cannot hold catches it wherever it lands.
BOOLEAN_VALUES = frozenset({"true", "false"})


class AskRequest(BaseModel):
    # module scope, not inside the handler: `from __future__ import annotations` plus a model
    # defined in a function raises PydanticUndefinedAnnotation (CLAUDE.md, known traps)
    question: str = Field(min_length=1, max_length=1000)


class FilterResolution(BaseModel):
    """How one filter value was resolved, rendered on the chip so a reader can see the
    difference between "the corpus carries this" and "the model typed this"."""

    raw: str
    #: "exact" | "embedding" | "verbatim" | "unresolved"
    method: str
    resolved: str | None = None
    similarity: float | None = None
    matter_count: int | None = None
    #: near misses, populated only when `method` is "unresolved"
    candidates: list[str] = Field(default_factory=list)
    note: str | None = None


class AskFilter(BaseModel):
    member: str
    operator: str
    #: the resolved values — what would actually be sent, not what the model typed
    values: list[str]
    resolutions: list[FilterResolution]


class AskUsage(BaseModel):
    """What the question cost, measured (#50). Every field comes from the response or the
    committed price table; none is estimated."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float
    price_checked_on: str
    price_source: str


class AskResponse(BaseModel):
    # `model_selection` collides with pydantic's protected `model_` namespace; the field is
    # named for the model's selection and renaming it to dodge a warning would make the
    # response read worse than the warning does.
    model_config = ConfigDict(protected_namespaces=())

    question: str
    measures: list[str]
    dimensions: list[str]
    filters: list[AskFilter]
    time_dimensions: list[dict[str, Any]]
    #: the model's output verbatim, so a reader can diff what it said against what will run
    model_selection: dict[str, Any]
    #: False when something must be fixed before this can execute — today, an unresolved value
    runnable: bool
    blocked_reason: str | None = None
    usage: AskUsage


def numeric_leaves(value: Any, path: str = "") -> list[str]:
    """Paths to every int or float in a decoded model response.

    Booleans count: `bool` is an `int` in Python and a model answering "true" to a question
    about a figure is still answering rather than selecting. Strings never count, even
    digit-only ones — `"2021"` is a legitimate signing-year filter value and the schema types
    filter values as strings.
    """
    if isinstance(value, dict):
        return [
            leaf for k, v in value.items() for leaf in numeric_leaves(v, f"{path}.{k}".lstrip("."))
        ]
    if isinstance(value, list):
        return [leaf for i, v in enumerate(value) for leaf in numeric_leaves(v, f"{path}[{i}]")]
    if isinstance(value, (int, float)):
        return [path]
    return []


def _resolve_values(
    member: str, values: list[str], vocabulary: Vocabulary
) -> tuple[list[str], list[FilterResolution], list[str]]:
    """Run one filter's values down the ladder. Returns the values to send, how each landed,
    and the reasons any of them blocks the run."""
    if vocabulary.type_of(member) == "boolean":
        # A type error, not a judgement call: no string but true/false can match, so this is
        # refused rather than left for the reader to spot.
        bad = [v for v in values if v.strip().lower() not in BOOLEAN_VALUES]
        if bad:
            return (
                [],
                [
                    FilterResolution(
                        raw=v,
                        method="unresolved",
                        candidates=["true", "false"],
                        note=(
                            f"{member.split('.')[-1]} is a yes/no field. No row can hold "
                            f"{v!r}, so this filter would return zero rows rather than an "
                            "answer."
                        ),
                    )
                    for v in bad
                ],
                [f"{member} is a yes/no field and cannot hold {', '.join(repr(v) for v in bad)}."],
            )

    if member not in RESOLVABLE_MEMBERS:
        note = (
            "Not an industry label, so the resolution ladder has no vocabulary to check it "
            "against. This is the model's own text — confirm it reads correctly."
        )
        return (
            list(values),
            [FilterResolution(raw=v, method="verbatim", resolved=v, note=note) for v in values],
            [],
        )

    resolved_values: list[str] = []
    resolutions: list[FilterResolution] = []
    blockers: list[str] = []

    # One connection and one cache for the whole filter set: the ladder reads the corpus's
    # distinct industry labels and the committed vectors, both of which are the same for
    # every value in the request.
    cache = EmbeddingCache(api_key=settings.openai_api_key)
    with psycopg.connect(settings.database_url) as conn:
        for raw in values:
            try:
                resolution = resolve_filter_value(conn, cache, raw)
            except UnresolvedFilterValue as unresolved:
                # Loud. The alternative is a filter nothing matches, and zero rows read as
                # "we have no comparable deals" rather than "you named something we do not
                # carry" — CLAUDE.md's nastiest failure mode in the design.
                resolutions.append(
                    FilterResolution(
                        raw=raw,
                        method="unresolved",
                        candidates=list(unresolved.candidates),
                        note=(
                            "The corpus carries no industry by this name. Pick one of the "
                            "near misses, or edit the chip."
                        ),
                    )
                )
                blockers.append(str(unresolved))
                continue
            resolved_values.append(resolution.resolved)
            resolutions.append(
                FilterResolution(
                    raw=resolution.raw,
                    method=resolution.method,
                    resolved=resolution.resolved,
                    similarity=resolution.similarity,
                    matter_count=resolution.matter_count,
                )
            )
    return resolved_values, resolutions, blockers


def _collapse(names: list[str]) -> list[str]:
    """First occurrence wins (#57).

    Asked "What's the average deal size for healthcare?" the model selected
    `comparable_deals.n` twice and the UI drew the same chip twice. A repeated name selects
    nothing a single one does not, so it is collapsed once here rather than in every client
    that renders a selection. Order is preserved: re-sorting would make the chips disagree
    with `model_selection`, which is shown beside them precisely so the two can be compared.
    """
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _collapse_filters(filters: list[AskFilter]) -> list[AskFilter]:
    """Two filters identical in member, operator and values are one filter.

    Two filters on the same member with *different* values are not: collapsing those would
    silently drop half of what was asked for, which is worse than drawing two chips.
    """
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    out: list[AskFilter] = []
    for f in filters:
        key = (f.member, f.operator, tuple(f.values))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _usage(call: SelectionCall) -> AskUsage:
    return AskUsage(
        model=call.model,
        prompt_tokens=call.prompt_tokens,
        completion_tokens=call.completion_tokens,
        latency_ms=call.latency_ms,
        cost_usd=cost_usd(call.model, call.prompt_tokens, call.completion_tokens),
        price_checked_on=PRICE_CHECKED_ON,
        price_source=PRICE_SOURCE,
    )


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    try:
        vocabulary: Vocabulary = fetch_vocabulary()
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not settings.openai_api_key:
        # Names the variable, carries no key material. There is no keyless promise to keep
        # since 7bc47ee — a key is required to run the product — but an unset variable must
        # still read as a configuration error rather than a stack trace.
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY is not set, so a question cannot be turned into a selection. "
                "Set it in .env and restart the API."
            ),
        )

    # Two small closed choices first — shape, then deal point. Measured 2026-09-06 on ten
    # questions a transactional lawyer would actually ask: the free-form path below answered
    # 0 of 10, this answers 6, and the four it declines are honest declines rather than a
    # count served in place of a distribution. See agent/shape.py for why.
    started = time.perf_counter()
    shaped_usage: list[tuple[int, int]] = []
    shaped = interpret(request.question, settings.openai_api_key, usage=shaped_usage)
    if shaped is not None:
        selection = shaped
        # Two calls, so the reported cost is their SUM. Latency is not summed from the parts —
        # it is measured around the whole thing below, because that is what the user waited.
        prompt_tokens = sum(p for p, _ in shaped_usage)
        completion_tokens = sum(c for _, c in shaped_usage)
        call = SelectionCall(
            selection=shaped,
            model=PICK_MODEL,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    else:
        # Falls back rather than refusing: the four shapes do not cover every answerable
        # question — "how many deals are all cash" filters a consideration type, not a deal
        # point — and a narrower path must not remove reach the wider one already had.
        call = select_with_usage(request.question, vocabulary, settings.openai_api_key)
        selection = call.selection

    numbers = numeric_leaves(selection)
    if numbers:
        # The model answered instead of selecting. Refuse rather than strip: a response that
        # carried a figure at all is not one to partially trust.
        log.warning("agent_ask_numeric_output", fields=numbers)
        raise HTTPException(
            status_code=422,
            detail=(
                "The model returned a number, which it must never do — it selects, Postgres "
                f"computes. Offending fields: {', '.join(numbers)}."
            ),
        )

    try:
        validate_selection(selection, vocabulary)
    except InvalidSelection as invalid:
        log.warning("agent_ask_rejected", reason=str(invalid))
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid

    filters: list[AskFilter] = []
    blockers: list[str] = []
    for f in selection.get("filters", []):
        values, resolutions, member_blockers = _resolve_values(
            f["member"], list(f.get("values", [])), vocabulary
        )
        blockers.extend(member_blockers)
        filters.append(
            AskFilter(
                member=f["member"],
                operator=f.get("operator", "equals"),
                values=values,
                resolutions=resolutions,
            )
        )

    filters = _collapse_filters(filters)
    measures = _collapse(list(selection.get("measures", [])))
    dimensions = _collapse(list(selection.get("dimensions", [])))

    usage = _usage(call)
    log.info(
        "agent_ask",
        model=usage.model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=usage.latency_ms,
        cost_usd=usage.cost_usd,
        measures=measures,
        collapsed=(
            len(selection.get("measures", []))
            + len(selection.get("dimensions", []))
            - len(measures)
            - len(dimensions)
        ),
        unresolved=len(blockers),
    )

    return AskResponse(
        question=request.question,
        measures=measures,
        dimensions=dimensions,
        filters=filters,
        time_dimensions=list(selection.get("timeDimensions", [])),
        model_selection=selection,
        runnable=not blockers,
        blocked_reason=" ".join(blockers) or None,
        usage=usage,
    )
