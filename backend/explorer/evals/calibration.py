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

**Human labels are read back into the score (#41).** Where the Label tab has recorded a decision
for the same `(matter_id, deal_point_name)`, that decision replaces the model's answer and is
then graded against MAUD exactly like the model's answer was — so a mistyped label lowers the
number. The before/after pair and the count of labels applied are written to
`docs/results/calibration-labels.json`, which the Admin tab renders.

What this does *not* claim: that this corpus needed the labels. Every matter in the holdout
already has a lawyer's answer in `deal_points`, so a reviewer here can only reproduce gold. The
mechanism is what generalizes to documents nobody annotated; the numbers it produces on MAUD are
a demonstration that the wiring exists, not evidence that human review beat the model.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

from explorer.api.settings import settings

ROOT = Path(__file__).resolve().parents[3]
SPLIT_FILE = ROOT / "docs" / "eval" / "calibration_split.json"
PREDICTIONS_FILE = ROOT / "docs" / "eval" / "calibration_predictions.json"
# committed; the Admin tab reads this rather than recomputing (#41)
LABEL_RESULTS_FILE = ROOT / "docs" / "results" / "calibration-labels.json"

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
    """`accuracy` is the graded number — the one #23's `reportable` gate reads. `*_before` is
    the same number with human labels excluded, kept alongside so the Admin table can show what
    the review queue actually moved instead of asserting that it moved something (#41)."""

    deal_point_name: str
    n: int
    correct: int
    accuracy: float
    ci_low: float
    ci_high: float
    reportable: bool
    correct_before: int
    accuracy_before: float
    labels_applied: int


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


def human_labels(keys: list[tuple[str, str]], dsn: str | None = None) -> dict[tuple[str, str], str]:
    """The rows the Label tab writes, keyed the way predictions are keyed (#41).

    `labels` is append-only — every keystroke is a row, so a reviewer who corrects themselves
    leaves two. The latest row per target wins; taking any other row would grade the extractor
    against a decision its reviewer already withdrew.

    Keys are passed in rather than parsed out of `target_id`, because `target_id` is
    `"{matter_id}:{deal_point_name}"` and deal point names contain colons.
    """
    if not keys:
        return {}
    by_target = {f"{matter_id}:{name}": (matter_id, name) for matter_id, name in keys}
    with psycopg.connect(dsn or settings.database_url) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (target_id) target_id, value
              FROM labels
             WHERE target_kind = 'deal_point'
               AND field = 'position'
               AND target_id = ANY(%(targets)s)
             ORDER BY target_id, updated_at DESC, id DESC
            """,
            {"targets": list(by_target)},
        ).fetchall()
    return {by_target[target]: value for target, value in rows if target in by_target}


def score(
    predictions: list[dict[str, Any]],
    actual: dict[tuple[str, str], str],
    labels: dict[tuple[str, str], str],
) -> dict[str, Any]:
    """Grade predictions against gold, preferring a human label over the model's answer for the
    same (matter_id, deal_point_name) (#41).

    Pure: no database, no key, no files — which is what makes the substitution rule testable at
    all. The rule is a *substitution*, not a correction: a label replaces the prediction and is
    then graded like any other answer, so a mistyped label lowers the score. Anything else would
    make the loop a ratchet that can only report improvement.
    """
    deal_point_names = sorted({p["deal_point_name"] for p in predictions})

    results: list[DealPointResult] = []
    labels_applied = 0
    labels_differing = 0
    for deal_point in deal_point_names:
        rows = [p for p in predictions if p["deal_point_name"] == deal_point]
        n = len(rows)
        correct_before = 0
        correct = 0
        applied = 0
        for p in rows:
            key = (p["matter_id"], deal_point)
            gold = actual.get(key)
            predicted = p["predicted_position"]
            graded = predicted
            if key in labels:
                graded = labels[key]
                applied += 1
                if graded != predicted:
                    labels_differing += 1
            correct_before += gold == predicted
            correct += gold == graded
        labels_applied += applied

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
                correct_before=correct_before,
                accuracy_before=round(correct_before / n if n else 0.0, 3),
                labels_applied=applied,
            )
        )

    total = sum(r.n for r in results)
    return {
        "deal_point_count": len(results),
        "prediction_count": len(predictions),
        "total_tokens": sum(p["tokens"] for p in predictions),
        "min_extraction_confidence": settings.min_extraction_confidence,
        "labels_applied": labels_applied,
        "labels_differing": labels_differing,
        "correct_before": sum(r.correct_before for r in results),
        "correct_after": sum(r.correct for r in results),
        "accuracy_before": (sum(r.correct_before for r in results) / total) if total else 0.0,
        "accuracy_after": (sum(r.correct for r in results) / total) if total else 0.0,
        "results": results,
    }


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


def grade(
    predictions_path: Path = PREDICTIONS_FILE,
    dsn: str | None = None,
    use_labels: bool = True,
) -> dict[str, Any]:
    """Offline: reads the committed predictions file, MAUD's own labels from `deal_points`, and
    the review queue's decisions from `labels`. No LLM call. Needs the corpus loaded, not a key.

    `use_labels=False` grades the extractor alone — the same number this function returned
    before #41, kept as a switch so "what did the humans change" is answerable by running the
    same code twice rather than by trusting a stored column.
    """
    predictions = json.loads(predictions_path.read_text())
    matter_ids = sorted({p["matter_id"] for p in predictions})
    deal_point_names = sorted({p["deal_point_name"] for p in predictions})
    actual = actual_positions(matter_ids, deal_point_names)
    keys = [(p["matter_id"], p["deal_point_name"]) for p in predictions]
    labels = human_labels(keys, dsn=dsn) if use_labels else {}
    return score(predictions, actual, labels)


def write_report(
    predictions_path: Path = PREDICTIONS_FILE,
    out_path: Path = LABEL_RESULTS_FILE,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Write the committed before/after artefact the Admin tab reads (#41).

    Admin renders a file rather than recomputing, for the reason the markdown report already
    gives: a number the UI computes on its own can drift from the number a reviewer reads in
    the repo, and then there are two.
    """
    summary = grade(predictions_path=predictions_path, dsn=dsn)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "PYTHONPATH=backend python -m explorer.evals.calibration",
        "prediction_count": summary["prediction_count"],
        "labels_applied": summary["labels_applied"],
        "labels_differing": summary["labels_differing"],
        "correct_before": summary["correct_before"],
        "correct_after": summary["correct_after"],
        "accuracy_before": round(summary["accuracy_before"], 3),
        "accuracy_after": round(summary["accuracy_after"], 3),
        "min_extraction_confidence": summary["min_extraction_confidence"],
        "results": [asdict(r) for r in summary["results"]],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    payload = write_report()
    for r in payload["results"]:
        print(r)
    print({k: v for k, v in payload.items() if k != "results"})
