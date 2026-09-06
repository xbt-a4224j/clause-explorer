"""NL -> Cube selection, enum-constrained at the schema level (#24).

The engineering claim CLAUDE.md makes: an agent answering analytical questions over legal data
has two independent ways to be wrong — the number, and the *definition* of the number.
Constraining the model to **select** from a versioned named-measure vocabulary instead of
generating SQL closes the second failure mode and makes the first one measurable offline.

**The model never produces a number.** It emits a *selection* — which measures, dimensions,
filters — validated against Cube's own `/meta`, then executed by this codebase exactly like any
other Cube query. There is no code path from the model's output to a displayed figure; the
figure always comes from `cube_client.query()`, the same function every other endpoint uses.

The vocabulary is read from `/meta` at call time, never hardcoded — a Cube model change (a new
measure, a renamed dimension) changes what the agent can select without a code change here,
and an invalid name becomes unrepresentable at JSON-schema decode time rather than merely
discouraged by a prompt.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from explorer.api.logging import get_logger
from explorer.api.settings import settings

log = get_logger()

# Only these two cubes/views are agent-selectable. `industries` is dimension metadata, not
# a fact table an agent should aggregate over.
SELECTABLE = {"comparable_deals", "deal_points"}

# The model file names this measure `..._do_not_use_for_market` specifically so a reader would
# not reach for it casually — but an enum that still lists the name makes it selectable
# regardless of what the name says. #27's eval measured this directly: asked for "the average
# reverse termination fee," the model selected exactly this measure. Structural exclusion is the
# only thing that actually enforces the intent the name states.
EXCLUDED_MEASURES = {"deal_points.mean_numeric_value_do_not_use_for_market"}


class AgentUnavailable(RuntimeError):
    """No key, or Cube's /meta did not answer. Never silently skipped."""


class InvalidSelection(RuntimeError):
    """The emitted selection references a measure, dimension, or filter member that /meta does
    not carry. Should be structurally impossible given the enum-constrained schema; still
    checked, because a schema bug or a model that ignores the schema must not reach Cube."""

    def __init__(self, message: str, selection: dict[str, Any]) -> None:
        self.selection = selection
        super().__init__(message)


@dataclass(frozen=True)
class Vocabulary:
    measures: tuple[str, ...]
    dimensions: tuple[str, ...]
    #: (dimension name, Cube type) pairs. A tuple rather than a dict so the dataclass stays
    #: hashable, and defaulted so every existing caller and test constructs one unchanged.
    #: Carried because a *string* filter value on a **boolean** dimension can never match a
    #: row: Cube returns zero rows, and zero rows read as "we have no comparable deals". The
    #: name alone cannot tell you that; the type can.
    dimension_types: tuple[tuple[str, str], ...] = ()

    def type_of(self, dimension: str) -> str | None:
        return dict(self.dimension_types).get(dimension)

    def as_json_schema_properties(self) -> dict[str, Any]:
        """The structured-output schema: measure/dimension NAMES are enums, so an invalid name
        cannot be decoded — not merely discouraged by instructions in the prompt."""
        return {
            "measures": {
                "type": "array",
                "items": {"type": "string", "enum": list(self.measures)},
            },
            "dimensions": {
                "type": "array",
                "items": {"type": "string", "enum": list(self.dimensions)},
            },
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "member": {
                            "type": "string",
                            "enum": list(self.measures + self.dimensions),
                        },
                        "operator": {"type": "string", "enum": ["equals", "contains", "gt", "lt"]},
                        "values": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["member", "operator", "values"],
                    "additionalProperties": False,
                },
            },
            "timeDimensions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dimension": {"type": "string", "enum": list(self.dimensions)},
                        "granularity": {"type": "string", "enum": ["day", "month", "year"]},
                    },
                    "required": ["dimension", "granularity"],
                    "additionalProperties": False,
                },
            },
        }


def fetch_vocabulary(cube_meta: dict[str, Any] | None = None) -> Vocabulary:
    """Reads Cube's live `/meta`. `cube_meta` is injectable for tests — never hardcode the
    vocabulary, but a test should not need a running Cube container to check parsing."""
    if cube_meta is None:
        try:
            response = httpx.get(f"{settings.cube_api_url}/meta", timeout=5.0)
            response.raise_for_status()
            cube_meta = response.json()
        except Exception as exc:  # one failure mode for the caller: AgentUnavailable
            raise AgentUnavailable("Cube's /meta did not answer.") from exc

    measures: list[str] = []
    dimensions: list[str] = []
    types: list[tuple[str, str]] = []
    for cube in cube_meta.get("cubes", []):
        if cube["name"] not in SELECTABLE:
            continue
        measures.extend(
            m["name"] for m in cube.get("measures", []) if m["name"] not in EXCLUDED_MEASURES
        )
        for d in cube.get("dimensions", []):
            dimensions.append(d["name"])
            if d.get("type"):
                types.append((d["name"], str(d["type"])))
    return Vocabulary(
        measures=tuple(measures),
        dimensions=tuple(dimensions),
        dimension_types=tuple(types),
    )


#: Measures that are meaningless unless the selection is scoped to ONE deal point.
#:
#: `numeric_value` is a single column carrying three incommensurable units — tail periods in
#: months, matching-rights periods in business days, and ownership thresholds in percent. A
#: percentile over the unscoped column is the median of {months, days, percent}: on this corpus
#: it evaluates to `4`, which is not a wrong quantity so much as not a quantity. The app served
#: exactly that in answer to "what's the average deal size".
#:
#: The Cube model has always said so — `median_numeric_value.description` reads "Filter by
#: deal_point_name first or this mixes days, months and percents into one meaningless number" —
#: and a test asserts that descriptions carry warnings like it. Nothing read the warning. A
#: description is documentation; this is the gate.
#:
#: Counts are deliberately absent: `n` and `numeric_n` count rows rather than averaging
#: quantities, so mixed units do not corrupt them and the guard must not touch them.
REQUIRES_SCOPE: dict[str, str] = {
    "deal_points.median_numeric_value": "deal_points.deal_point_name",
    "deal_points.p25_numeric_value": "deal_points.deal_point_name",
    "deal_points.p75_numeric_value": "deal_points.deal_point_name",
}

#: Said in the measure's own words rather than a second wording that can drift from it.
SCOPE_REASON = (
    "it averages a column that holds several units at once — tail periods in months, "
    "matching-rights periods in business days, ownership thresholds in percent — so an "
    "unscoped percentile mixes them into a number with no unit"
)


def _is_scoped_to_one(selection: dict[str, Any], member: str) -> bool:
    """Whether the selection pins `member` to a single value, either way that counts.

    Grouping by it is as good as filtering to one: one row per deal point means each
    percentile falls inside a single unit. Refusing the grouped form would be the kind of
    over-refusal that gets a gate switched off rather than fixed.
    """
    if member in selection.get("dimensions", []):
        return True
    return any(
        f.get("member") == member
        and f.get("operator", "equals") == "equals"
        and len(f.get("values") or []) == 1
        for f in selection.get("filters", [])
    )


def validate_selection(selection: dict[str, Any], vocabulary: Vocabulary) -> None:
    """Defense in depth: the schema should make an invalid name undecidable, but this is the
    one gate every selection passes through before it reaches Cube, schema behaved or not."""
    allowed = set(vocabulary.measures) | set(vocabulary.dimensions)
    for measure in selection.get("measures", []):
        if measure not in vocabulary.measures:
            raise InvalidSelection(f"{measure!r} is not a known measure.", selection)
        required = REQUIRES_SCOPE.get(measure)
        if required and not _is_scoped_to_one(selection, required):
            raise InvalidSelection(
                f"{measure!r} needs {required!r} pinned to one value, because "
                f"{SCOPE_REASON}. Filter to a single deal point, or group by "
                f"{required!r} so each row stays inside one unit.",
                selection,
            )
    for dimension in selection.get("dimensions", []):
        if dimension not in vocabulary.dimensions:
            raise InvalidSelection(f"{dimension!r} is not a known dimension.", selection)
    for f in selection.get("filters", []):
        if f.get("member") not in allowed:
            raise InvalidSelection(f"{f.get('member')!r} is not a selectable field.", selection)
    for td in selection.get("timeDimensions", []):
        if td.get("dimension") not in vocabulary.dimensions:
            raise InvalidSelection(f"{td.get('dimension')!r} is not a known dimension.", selection)


SYSTEM_PROMPT = (
    "You translate a legal analyst's question into a Cube.js query selection. You select from "
    "the provided measure and dimension names only — you never invent a name, and you never "
    "compute or state a number yourself. Return only the selection."
)


#: the one model this codebase calls for selection. Named here rather than inline so the
#: price table in `evals/pricing.py` and the call site cannot name two different models.
SELECT_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class SelectionCall:
    """One model call, with what it cost to make.

    The token counts and latency are measured from the response, not estimated: #50 renders
    them to the user and CLAUDE.md forbids a plausible invented number anywhere a figure is
    published. Dollars are deliberately absent — they are priced by `evals/pricing.py` from
    these counts, so there is one place the price table is read.
    """

    selection: dict[str, Any]
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


def select_with_usage(question: str, vocabulary: Vocabulary, api_key: str) -> SelectionCall:
    """The only function in this module that calls out. Everything else is pure and testable
    with no key."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    schema = {
        "type": "object",
        "properties": vocabulary.as_json_schema_properties(),
        "required": ["measures", "dimensions", "filters", "timeDimensions"],
        "additionalProperties": False,
    }
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=SELECT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "cube_selection", "schema": schema, "strict": True},
        },
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    content = response.choices[0].message.content
    usage = response.usage
    log.info(
        "agent_llm_call",
        model=SELECT_MODEL,
        tokens=usage.total_tokens if usage else None,
        latency_ms=latency_ms,
    )
    return SelectionCall(
        selection=dict(json.loads(content or "{}")),
        model=SELECT_MODEL,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        latency_ms=latency_ms,
    )


def select_via_llm(question: str, vocabulary: Vocabulary, api_key: str) -> dict[str, Any]:
    """The selection alone, for callers with nothing to do with the usage — the eval recorder
    grades selections and has no cost line to render."""
    return select_with_usage(question, vocabulary, api_key).selection
