"""`GET /label/queue`, `POST /label/decide` — the review queue (#29).

Improvement has to be cheap or it will not happen: uncertainty sampling and disagreement mining
make 50 labels worth more than 500 random ones. The queue is built from #28's already-committed
LLM extractor output (`docs/eval/calibration_predictions.json` — real, recorded, no new API
call to serve this) scored against a keyword-count baseline that costs nothing per item. Ranking
by *disagreement between the two* needs no calibrated confidence — the cheapest useful signal
available before #28 has measured one for a given deal point.

Accepting an item writes a new row to `labels`. Since #41 the calibration grader reads that
table: the latest decision for a `(matter_id, deal_point_name)` replaces the model's answer and
is then graded against MAUD like any other answer, so a mistyped label lowers the accuracy
figure. What that does not buy is a better answer on *this* corpus — every queued item is a
held-out matter that already has a lawyer's answer, so a reviewer here can only reproduce gold.
The mechanism is for un-annotated documents; MAUD is where it can be measured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.agent.deterministic_extract import predict_deterministic
from explorer.api.logging import get_logger
from explorer.api.matters import _read_source
from explorer.api.settings import settings

router = APIRouter(prefix="/label")
log = get_logger()

ROOT = Path(__file__).resolve().parents[3]
PREDICTIONS_FILE = ROOT / "docs" / "eval" / "calibration_predictions.json"


class QueueItem(BaseModel):
    matter_id: str
    deal_point_name: str
    llm_prediction: str
    deterministic_prediction: str
    disagreement: bool
    quoted_text: str | None
    span_start: int | None
    span_end: int | None


class QueueResponse(BaseModel):
    items: list[QueueItem]
    queue_size: int
    labelled_count: int


@router.get("/queue", response_model=QueueResponse)
def queue() -> QueueResponse:
    if not PREDICTIONS_FILE.is_file():
        raise HTTPException(
            status_code=404,
            detail="No recorded predictions yet — run "
            '`python -c "from explorer.evals.calibration import record_predictions; '
            'record_predictions()"` (needs a key) and commit '
            "docs/eval/calibration_predictions.json.",
        )

    import json

    predictions = json.loads(PREDICTIONS_FILE.read_text())
    matter_ids = sorted({p["matter_id"] for p in predictions})

    with psycopg.connect(settings.database_url) as conn:
        source_rows = conn.execute(
            "SELECT id, source_file FROM matters WHERE id = ANY(%(ids)s)", {"ids": matter_ids}
        ).fetchall()
        labelled_row = conn.execute(
            "SELECT count(*) FROM labels WHERE target_kind = 'deal_point'"
        ).fetchone()
        labelled_count = labelled_row[0] if labelled_row else 0

        allowed_by_point: dict[str, list[str]] = {}
        for name in {p["deal_point_name"] for p in predictions}:
            rows = conn.execute(
                "SELECT DISTINCT position FROM deal_points WHERE deal_point_name = %s", (name,)
            ).fetchall()
            allowed_by_point[name] = sorted({r[0] for r in rows})

    sources: dict[str, str] = dict(source_rows)

    items: list[QueueItem] = []
    for p in predictions:
        text = _read_source(sources.get(p["matter_id"])) or ""
        deterministic = predict_deterministic(
            text, p["deal_point_name"], allowed_by_point.get(p["deal_point_name"], [])
        )
        disagreement = deterministic != p["predicted_position"]
        items.append(
            QueueItem(
                matter_id=p["matter_id"],
                deal_point_name=p["deal_point_name"],
                llm_prediction=p["predicted_position"],
                deterministic_prediction=deterministic,
                disagreement=disagreement,
                quoted_text=p.get("quoted_text"),
                span_start=p.get("span_start"),
                span_end=p.get("span_end"),
            )
        )

    # Disagreement first — the cheapest useful ranking signal with no calibrated confidence.
    items.sort(key=lambda i: (not i.disagreement, i.matter_id, i.deal_point_name))

    return QueueResponse(items=items, queue_size=len(items), labelled_count=int(labelled_count))


class DecideRequest(BaseModel):
    matter_id: str = Field(min_length=1)
    deal_point_name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    prior_prediction: str | None = None


@router.post("/decide")
def decide(request: DecideRequest) -> dict[str, Any]:
    """Accept, reject-and-correct, or (via a different `value`) overwrite a prediction. Every
    call writes a row — there is no separate "reject" verb, because a reject with no correction
    would just be silence, and silence does not become a label #28 can grade against."""
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            """
            INSERT INTO labels (target_kind, target_id, field, value, prior_prediction, labeller)
            VALUES ('deal_point', %(target_id)s, 'position', %(value)s, %(prior)s, 'local')
            """,
            {
                "target_id": f"{request.matter_id}:{request.deal_point_name}",
                "value": request.value,
                "prior": request.prior_prediction,
            },
        )
    log.info(
        "label_decided",
        matter_id=request.matter_id,
        deal_point_name=request.deal_point_name,
        value=request.value,
    )
    return {"ok": True}
