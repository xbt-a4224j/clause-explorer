"""`POST /agent/members` (#57) — what a selected name means, and whether the corpus can
answer with it.

## Why this exists

Ask asked *"What's the average deal size for healthcare?"* and drew three chips reading
`measure n`, `measure n`, and `has_industry` over an empty text box. Every fault in that line
is a question about the corpus that the frontend had no way to ask:

* **What is this called.** Cube's `/meta` carries a `title` and a `description` for every
  measure and dimension. The chip rendered the bare member suffix and threw both away.
* **What may it hold.** Every dimension in this model is a closed vocabulary — the values are
  corpus content — so a filter on one has a knowable candidate set and never needs free text.
* **Can the corpus answer at all.** `deal_value_usd` is NULL for all 152 matters, so
  `deal_size_band` holds one value, `unknown`. No selection over it can produce a figure. A
  tool that fails and a tool that says why it cannot answer are different products.

## Why it is not part of `/agent/ask`

`ask.py` must never touch Cube's `/load`, and a test there asserts it on every path including
the reject paths. That property is what makes the confirmation step mean anything: the model
selects, a person confirms, and only then does a query run. Corpus coverage is a query, so it
lives here and the frontend asks for it once the selection is back. The two round trips are
the honest shape of it.

## The emptiness check is a probe, not a list

Nothing here names a column. Coverage is read from Cube for whatever member was asked about,
so a column that fills up stops being reported the moment it does, and a column that empties
starts being reported without a code change. A hardcoded list of known-empty columns would be
right today and wrong silently.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.api.cube_client import CubeUnavailable, meta
from explorer.api.cube_client import query as cube_query
from explorer.api.logging import get_logger

router = APIRouter(prefix="/agent")
log = get_logger()

#: Past this many distinct values a select stops being usable and a text box would be the only
#: option left. Measured on the loaded corpus, the widest dimension is `deal_points.position`
#: at 225 distinct answers and `deal_points.deal_point_name` at 92, so **nothing here reaches
#: the cap** — every dimension in this model enumerates and no filter value needs free text.
#: The branch is kept as a guard against a corpus that grows past it, not as a live path.
#:
#:     docker exec clause-explorer-db-1 psql -U explorer -d explorer -Atc \
#:       "select count(distinct position) from deal_points;"   ->  225
CANDIDATE_LIMIT = 500

#: Cube renders booleans as these two strings, and they are also what the dimension will accept
#: back as a filter value. Not read from the data: a boolean column that happens to hold only
#: TRUE today still has exactly two possible values.
BOOLEAN_VALUES = ["false", "true"]


class MemberInfo(BaseModel):
    """One name from a selection, with everything needed to render a chip a person can read,
    confirm and correct."""

    name: str
    #: the catalog's own title, e.g. "Deal Points N". Falls back to `name` when unknown.
    title: str
    description: str
    #: "measure" | "dimension" | "unknown"
    kind: str
    #: Cube's type for the member, e.g. "count", "string", "boolean". Empty when unknown.
    type: str = ""
    #: the values the corpus holds for this dimension, when they can be enumerated
    candidates: list[str] = Field(default_factory=list)
    #: True only when `candidates` is the complete set. A truncated list is not a vocabulary.
    enumerable: bool = False
    #: how many distinct non-null values exist, whether or not they were listed
    distinct_values: int = 0
    #: rows carrying a value / rows in the cube. None when coverage could not be probed.
    populated: int | None = None
    total: int | None = None
    #: set when no selection over this member can produce an answer, saying why in full
    cannot_answer: str | None = None


class MembersRequest(BaseModel):
    names: list[str] = Field(default_factory=list, max_length=32)


class MembersResponse(BaseModel):
    members: list[MemberInfo]


def _catalog(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every measure and dimension in `/meta`, flattened by name and tagged with which it is."""
    entries: dict[str, dict[str, Any]] = {}
    for cube in body.get("cubes", []):
        for kind, key in (("measure", "measures"), ("dimension", "dimensions")):
            for item in cube.get(key, []):
                name = str(item.get("name", ""))
                if not name:
                    continue
                entries[name] = {
                    "kind": kind,
                    "cube": str(cube.get("name", "")),
                    "title": str(item.get("title") or name),
                    "description": str(item.get("description") or ""),
                    "type": str(item.get("type") or ""),
                }
    return entries


def _count_measure(body: dict[str, Any], cube_name: str) -> str | None:
    """The measure that answers "how many rows" for a cube.

    By convention every cube in this model publishes `<cube>.n` and the docstrings on it call
    it THE DENOMINATOR. Falling back to whatever count-typed measure exists keeps a new cube
    from silently losing its coverage line.
    """
    for cube in body.get("cubes", []):
        if cube.get("name") != cube_name:
            continue
        names = [str(m.get("name", "")) for m in cube.get("measures", [])]
        if f"{cube_name}.n" in names:
            return f"{cube_name}.n"
        for m in cube.get("measures", []):
            if str(m.get("type")) == "count":
                return str(m.get("name"))
    return None


def _dimension_info(info: MemberInfo, entry: dict[str, Any], body: dict[str, Any]) -> None:
    """Fill in candidates and coverage for a dimension, from one grouped Cube query."""
    counter = _count_measure(body, entry["cube"])
    # No truncating limit: `distinct_values` below is published as a count and a count that
    # silently stops at the cap is a wrong number that looks right. The widest dimension in
    # this corpus is 225 rows.
    payload: dict[str, Any] = {"dimensions": [info.name], "limit": 5000}
    if counter:
        payload["measures"] = [counter]
    rows = cube_query(payload)

    values: list[str] = []
    populated = 0
    total = 0
    for row in rows:
        raw = row.get(info.name)
        n = int(row.get(counter) or 0) if counter else 0
        total += n
        if raw is None or raw == "":
            continue
        populated += n
        values.append("true" if raw is True else "false" if raw is False else str(raw))

    info.distinct_values = len(values)
    if entry["type"] == "boolean":
        # Two values by definition, whichever of them the corpus happens to carry today.
        info.candidates = list(BOOLEAN_VALUES)
        info.enumerable = True
    elif len(values) <= CANDIDATE_LIMIT:
        info.candidates = sorted(values)
        info.enumerable = True
    else:
        # Deliberately empty rather than truncated: a short list that looks like the vocabulary
        # is worse than saying it was not enumerated.
        info.candidates = []
        info.enumerable = False

    if counter:
        info.populated = populated
        info.total = total

    if info.distinct_values == 0:
        info.cannot_answer = (
            f"{info.title} is empty across the corpus — "
            f"{_of(0, info.total)} carry a value — so no selection over it can return a "
            "figure. This is the corpus, not the query: nothing here needs repairing."
        )
    elif info.distinct_values == 1:
        info.cannot_answer = (
            f"{info.title} holds one value across the whole corpus, "
            f"{values[0]!r}, on {_of(populated, info.total)}. Grouping or filtering by it "
            "cannot separate anything, so it cannot answer a question about it."
        )


def _measure_info(info: MemberInfo, body: dict[str, Any], cube_name: str) -> None:
    """Probe a measure over the whole corpus. A measure that is null with no filter applied at
    all has no rows anywhere to compute from — the median of a column carrying no numbers."""
    rows = cube_query({"measures": [info.name]})
    value = rows[0].get(info.name) if rows else None
    counter = _count_measure(body, cube_name)
    if counter and counter != info.name:
        count_rows = cube_query({"measures": [counter]})
        info.total = int(count_rows[0].get(counter) or 0) if count_rows else None
    elif value is not None:
        info.total = int(value)

    if value is None:
        info.cannot_answer = (
            f"{info.title} computes to nothing over the whole corpus — the column behind it "
            "carries no values — so no slice of it can carry one either. This is the corpus, "
            "not the query: nothing here needs repairing."
        )


def _of(populated: int, total: int | None) -> str:
    """ "0 of 152", the house format. Never a bare count and never a percentage."""
    return f"{populated} of {total}" if total else str(populated)


def describe(names: list[str]) -> list[MemberInfo]:
    """Order-preserving, de-duplicated. The model duplicated `comparable_deals.n` in the
    selection that opened #57; probing it twice would be the same sloppiness one layer down."""
    body = meta()
    entries = _catalog(body)

    seen: set[str] = set()
    out: list[MemberInfo] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        entry = entries.get(name)
        if entry is None:
            # Reported, not dropped. A chip with no title and no reason for it is the fault
            # this endpoint exists to fix.
            out.append(
                MemberInfo(
                    name=name,
                    title=name,
                    description="",
                    kind="unknown",
                    cannot_answer=(
                        f"{name} is not in the semantic layer's vocabulary, so nothing is "
                        "known about what it means or what it may hold."
                    ),
                )
            )
            continue
        info = MemberInfo(
            name=name,
            title=entry["title"],
            description=entry["description"],
            kind=entry["kind"],
            type=entry["type"],
        )
        if entry["kind"] == "dimension":
            _dimension_info(info, entry, body)
        else:
            _measure_info(info, body, entry["cube"])
        out.append(info)
    return out


@router.post("/members", response_model=MembersResponse)
def members(request: MembersRequest) -> MembersResponse:
    try:
        described = describe(request.names)
    except CubeUnavailable as unavailable:
        # "Nothing is known about this member" and "the semantic layer is unreachable" are
        # different statements, and the chip renders them differently.
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    log.info(
        "agent_members",
        asked=len(request.names),
        described=len(described),
        cannot_answer=[m.name for m in described if m.cannot_answer],
    )
    return MembersResponse(members=described)
