"""`GET /agent/catalog` (#36) — the vocabulary a selection may draw from.

This endpoint is the semantic-layer argument in one response. An agent answering analytical
questions has two independent ways to be wrong: the number, and the *definition* of the
number. Freeform text-to-SQL leaves both open and gives you nothing to grade — two generated
queries can only be diffed, not scored.

Constraining the model to select from named measures closes the second failure and makes the
first discrete: did it pick the right measure and filters, yes or no. `label_space` is that
claim made numeric — it is the size of the set an offline eval grades against, with no
database and no model in the loop.

Read live from Cube rather than checked in, because a stale copy would let the catalog and
`cube/model/*.yml` disagree, and then a selection failure becomes an argument about which
list was authoritative.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from explorer.agent.select import EXCLUDED_MEASURES, SELECTABLE
from explorer.api.cube_client import CubeUnavailable, meta
from explorer.api.logging import get_logger

router = APIRouter(prefix="/agent")
log = get_logger()


class CatalogEntry(BaseModel):
    name: str
    title: str
    type: str
    cube: str
    #: why this exists and what it counts. A catalog without descriptions is a list of opaque
    #: identifiers, and a selection over opaque identifiers cannot be reviewed by the one
    #: person qualified to catch a misinterpretation.
    description: str = ""


class CatalogResponse(BaseModel):
    measures: list[CatalogEntry]
    dimensions: list[CatalogEntry]
    #: measures + dimensions: the discrete label space a selection is graded against
    label_space: int


def _entries(cubes: list[dict[str, Any]], key: str) -> list[CatalogEntry]:
    """Only what a selection may actually draw from.

    `SELECTABLE` and `EXCLUDED_MEASURES` are imported from `agent/select.py` rather than
    restated, because `validate_selection` rejects anything outside them and this endpoint feeds
    a picker. Two lists would be two answers to "what can I select", and the one the user reads
    would be the one that is wrong.

    It was wrong. Walking the Ask tab, the builder offered `matters.industry_code` and
    `industries.label`, and `POST /agent/run-selection` answered "'matters.industry_code' is not
    a known dimension" — an error the UI produced by offering the option. `label_space` was
    published as 48 under the claim "the model chooses from these names and no others"; the
    model chose from 30.
    """
    return [
        CatalogEntry(
            name=str(item.get("name", "")),
            title=str(item.get("title", "")),
            type=str(item.get("type", "")),
            cube=str(cube.get("name", "")),
            description=str(item.get("description") or ""),
        )
        for cube in cubes
        if cube.get("name") in SELECTABLE
        for item in cube.get(key, [])
        if item.get("name") not in EXCLUDED_MEASURES
    ]


@router.get("/catalog", response_model=CatalogResponse)
def catalog() -> CatalogResponse:
    try:
        body = meta()
    except CubeUnavailable as unavailable:
        # An empty catalog would read as "the model may select nothing" — a different and
        # much worse claim than "the semantic layer is unreachable".
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    cubes = list(body.get("cubes", []))
    measures = _entries(cubes, "measures")
    dimensions = _entries(cubes, "dimensions")
    log.info("catalog_read", measures=len(measures), dimensions=len(dimensions))
    return CatalogResponse(
        measures=measures,
        dimensions=dimensions,
        label_space=len(measures) + len(dimensions),
    )
