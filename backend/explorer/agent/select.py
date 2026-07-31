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
from dataclasses import dataclass
from typing import Any

import httpx

from explorer.api.logging import get_logger
from explorer.api.settings import settings

log = get_logger()

# Only these two cubes/views are agent-selectable. `folio_concepts` is dimension metadata, not
# a fact table an agent should aggregate over.
SELECTABLE = {"comparable_deals", "deal_points"}


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
    for cube in cube_meta.get("cubes", []):
        if cube["name"] not in SELECTABLE:
            continue
        measures.extend(m["name"] for m in cube.get("measures", []))
        dimensions.extend(d["name"] for d in cube.get("dimensions", []))
    return Vocabulary(measures=tuple(measures), dimensions=tuple(dimensions))


def validate_selection(selection: dict[str, Any], vocabulary: Vocabulary) -> None:
    """Defense in depth: the schema should make an invalid name undecidable, but this is the
    one gate every selection passes through before it reaches Cube, schema behaved or not."""
    allowed = set(vocabulary.measures) | set(vocabulary.dimensions)
    for measure in selection.get("measures", []):
        if measure not in vocabulary.measures:
            raise InvalidSelection(f"{measure!r} is not a known measure.", selection)
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


def select_via_llm(question: str, vocabulary: Vocabulary, api_key: str) -> dict[str, Any]:
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
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "cube_selection", "schema": schema, "strict": True},
        },
    )
    content = response.choices[0].message.content
    log.info(
        "agent_llm_call",
        model="gpt-4o-mini",
        tokens=response.usage.total_tokens if response.usage else None,
    )
    return dict(json.loads(content or "{}"))
