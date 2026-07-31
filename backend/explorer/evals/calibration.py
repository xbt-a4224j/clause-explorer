"""Calibration: extractor vs held-out MAUD labels, per deal point with CI (#28).

Runs the minimal extractor (`extract_deal_point.py`) over the committed holdout split
(`docs/eval/calibration_split.json`) for a fixed slice of deal points, compares predictions
against MAUD's own labels, and reports accuracy per deal point with a binomial confidence
interval and its own n — a bare "87%" with no denominator violates the project's own rule
(CLAUDE.md).

**Held out means held out.** These matters are never used to tune the extractor's prompt or
choose the deal-point slice; the slice was chosen for the *shape* of its position vocabulary
(small, closed) before any prediction was run, off the full corpus's distribution, not the
holdout's.

Needs `OPENAI_API_KEY` to produce new predictions; grading a committed predictions file does
not.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg

from explorer.api.settings import settings

ROOT = Path(__file__).resolve().parents[3]
SPLIT_FILE = ROOT / "docs" / "eval" / "calibration_split.json"
PREDICTIONS_FILE = ROOT / "docs" / "eval" / "calibration_predictions.json"

# Chosen for a small, closed position vocabulary (binary Y/N-style points, fully answered
# across the corpus) — chosen before any prediction was run, off the corpus-wide distribution,
# not the holdout's, to keep the holdout genuinely unseen during selection.
DEAL_POINTS = [
    "Announcement, pendency or consummation of deal (Y/N)",
    '"Ability to consummate" concept is subject to MAE carveouts',
    "Actions taken by Buyer-Answer (Y/N)",
    "Acquisition Proposal required to be publicly disclosed-Answer (Y/N)",
    "Action prohibited/omission required by the agreement-Answer",
]


@dataclass(frozen=True)
class DealPointResult:
    deal_point_name: str
    n: int
    correct: int
    accuracy: float
    ci_low: float
    ci_high: float
    reportable: bool


def wilson_interval(correct: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval — stable at small n and at accuracy near 0 or 1, unlike the
    normal approximation, which can produce bounds outside [0, 1]."""
    if n == 0:
        return 0.0, 0.0
    phat = correct / n
    denom = 1 + z**2 / n
    center = phat + z**2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n)
    return max(0.0, (center - margin) / denom), min(1.0, (center + margin) / denom)


def actual_positions(
    matter_ids: list[str], deal_point_names: list[str]
) -> dict[tuple[str, str], str]:
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT matter_id, deal_point_name, position FROM deal_points "
            "WHERE matter_id = ANY(%(ids)s) AND deal_point_name = ANY(%(names)s)",
            {"ids": matter_ids, "names": deal_point_names},
        ).fetchall()
    return {(m, d): p for m, d, p in rows}


def record_predictions(dsn: str | None = None) -> list[dict[str, Any]]:
    """The only function here that calls out. Produces `calibration_predictions.json`."""
    from explorer.evals.extract_deal_point import predict

    if not settings.has_openai_key or settings.openai_api_key is None:
        raise SystemExit("calibration needs OPENAI_API_KEY.")

    split = json.loads(SPLIT_FILE.read_text())
    holdout = split["holdout_matter_ids"]

    with psycopg.connect(dsn or settings.database_url) as conn:
        rows = conn.execute(
            "SELECT id, source_file FROM matters WHERE id = ANY(%(ids)s)", {"ids": holdout}
        ).fetchall()
    sources: dict[str, str] = dict(rows)

    # `source_file` is recorded relative to `data/`, not the repo root (the same convention
    # `api/matters.py`'s DATA_ROOT follows) — joining it under the MAUD corpus root directly,
    # as an earlier version of this function did, silently produced zero matches.
    data_root = ROOT / "data"

    predictions = []
    for matter_id in holdout:
        source_file = sources.get(matter_id)
        if not source_file:
            continue
        path = data_root / source_file
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")

        for deal_point in DEAL_POINTS:
            with psycopg.connect(dsn or settings.database_url) as conn:
                positions_rows = conn.execute(
                    "SELECT DISTINCT position FROM deal_points WHERE deal_point_name = %s",
                    (deal_point,),
                ).fetchall()
            allowed = sorted({r[0] for r in positions_rows})

            result = predict(matter_id, text, deal_point, allowed, settings.openai_api_key)
            predictions.append(asdict(result))

    PREDICTIONS_FILE.write_text(json.dumps(predictions, indent=2) + "\n")
    return predictions


def grade(predictions_path: Path = PREDICTIONS_FILE, dsn: str | None = None) -> dict[str, Any]:
    """Offline: reads the committed predictions file and MAUD's own labels from the DB, no
    LLM call. Needs the corpus loaded, not a key."""
    predictions = json.loads(predictions_path.read_text())
    matter_ids = sorted({p["matter_id"] for p in predictions})
    deal_point_names = sorted({p["deal_point_name"] for p in predictions})
    actual = actual_positions(matter_ids, deal_point_names)

    results: list[DealPointResult] = []
    for deal_point in deal_point_names:
        rows = [p for p in predictions if p["deal_point_name"] == deal_point]
        n = len(rows)
        correct = sum(
            1 for p in rows if actual.get((p["matter_id"], deal_point)) == p["predicted_position"]
        )
        accuracy = correct / n if n else 0.0
        ci_low, ci_high = wilson_interval(correct, n)
        results.append(
            DealPointResult(
                deal_point_name=deal_point,
                n=n,
                correct=correct,
                accuracy=round(accuracy, 3),
                ci_low=round(ci_low, 3),
                ci_high=round(ci_high, 3),
                reportable=ci_low >= settings.min_extraction_confidence,
            )
        )

    total_tokens = sum(p["tokens"] for p in predictions)
    return {
        "deal_point_count": len(results),
        "prediction_count": len(predictions),
        "total_tokens": total_tokens,
        "min_extraction_confidence": settings.min_extraction_confidence,
        "results": results,
    }


if __name__ == "__main__":
    summary = grade()
    for r in summary["results"]:
        print(r)
    print(
        {k: v for k, v in summary.items() if k != "results"},
    )
