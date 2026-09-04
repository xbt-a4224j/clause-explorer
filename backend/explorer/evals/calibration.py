"""Calibration: extractor vs held-out MAUD labels, per deal point with CI (#28, widened in #44).

Runs the minimal extractor (`extract_deal_point.py`) over the committed holdout split
(`docs/eval/calibration_split.json`) for **every deal point in the corpus vocabulary**, compares
predictions against MAUD's own labels, and reports accuracy per deal point with a binomial
confidence interval and its own n — a bare "87%" with no denominator violates the project's own
rule (CLAUDE.md).

#28 calibrated 5 hand-picked deal points, all with a small closed position vocabulary. That is
5% of the label space and it was chosen for being easy to grade, which biases the sample toward
the easy end of the task. #44 removes the hardcoded list: the vocabulary is read from the data,
so a 93rd deal point is measured the day it lands (D8's long shape, again).

**Held out means held out.** These matters are never used to tune the extractor's prompt. With
the deal-point slice no longer chosen by hand, there is nothing left to choose — the run covers
everything MAUD labelled on the holdout.

**Only labelled pairs are scheduled.** MAUD does not answer every deal point for every
agreement. Predicting an unanswered pair would be graded against a label that does not exist,
producing a fabricated error rate and paying real tokens for it.

Needs `OPENAI_API_KEY` to produce new predictions; grading a committed predictions file does
not.
"""

from __future__ import annotations

import json
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg

from explorer.api.logging import get_logger
from explorer.api.settings import settings
from explorer.evals.pricing import PRICE_CHECKED_ON, PRICE_SOURCE, cost_usd

log = get_logger()

ROOT = Path(__file__).resolve().parents[3]
SPLIT_FILE = ROOT / "docs" / "eval" / "calibration_split.json"
PREDICTIONS_FILE = ROOT / "docs" / "eval" / "calibration_predictions.json"
COST_FILE = ROOT / "docs" / "eval" / "calibration_cost.json"
ACCURACY_FILE = ROOT / "docs" / "eval" / "calibration_accuracy.json"

# Concurrency, not parallelism: these calls are I/O-bound (each waits on the OpenAI API), so
# interleaving them is the whole win. Kept modest so a run cannot look like an attack on the
# rate limit; the run is minutes either way.
MAX_WORKERS = 8

# Six attempts with jittered exponential backoff. Three flat retries lost 19% of #44's first
# pass to rate limits; the tail here reaches ~32s, which is longer than the limit windows that
# dropped those calls.
MAX_ATTEMPTS = 6


@dataclass(frozen=True)
class DealPointResult:
    deal_point_name: str
    n: int
    correct: int
    # None, not 0.0, when nothing was measured. "We got none right" and "we never asked" are
    # different findings and must not render alike.
    accuracy: float | None
    ci_low: float | None
    ci_high: float | None
    reportable: bool
    measured: bool


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


def deal_point_vocabulary(dsn: str | None = None) -> list[str]:
    """Every deal point the corpus knows about, read from the data rather than hardcoded."""
    with psycopg.connect(dsn or settings.database_url) as conn:
        rows = conn.execute(
            "SELECT DISTINCT deal_point_name FROM deal_points ORDER BY deal_point_name"
        ).fetchall()
    return [r[0] for r in rows]


def holdout_pairs(dsn: str | None = None) -> list[tuple[str, str]]:
    """The (matter, deal point) pairs to predict: exactly those MAUD labelled on the holdout.

    This is the unit of cost. Scheduling the full cross product instead would buy predictions
    that cannot be graded, at the same price per call.
    """
    holdout = json.loads(SPLIT_FILE.read_text())["holdout_matter_ids"]
    with psycopg.connect(dsn or settings.database_url) as conn:
        rows = conn.execute(
            "SELECT matter_id, deal_point_name FROM deal_points WHERE matter_id = ANY(%(ids)s) "
            "ORDER BY matter_id, deal_point_name",
            {"ids": holdout},
        ).fetchall()
    return [(m, d) for m, d in rows]


def missing_pairs(
    scheduled: list[tuple[str, str]], recorded: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    """Scheduled pairs with no recorded prediction, in scheduled order.

    The unit of a resumed run. Rate limits dropped 325 of #44's first 1,704 calls; paying for
    the 1,379 that landed a second time would put a number in the cost file that is larger than
    the table actually cost to produce.
    """
    have = {(p["matter_id"], p["deal_point_name"]) for p in recorded}
    return [pair for pair in scheduled if pair not in have]


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


def run_cost(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    """The run's measured cost, priced from each call's own token split.

    Input and output are summed separately because they are priced separately; the #28 run
    could only publish a range because it recorded totals alone.
    """
    # A prediction recorded before #44 has a total-token count and no split, so it cannot be
    # priced. It is counted and named rather than silently treated as free — a $0.00 for a call
    # that really cost something is a fabricated number.
    priced = [p for p in predictions if p.get("model") and "prompt_tokens" in p]
    unpriced = len(predictions) - len(priced)
    prompt_tokens = sum(int(p["prompt_tokens"]) for p in priced)
    completion_tokens = sum(int(p["completion_tokens"]) for p in priced)
    models = sorted({str(p["model"]) for p in priced})
    total = sum(
        cost_usd(str(p["model"]), int(p["prompt_tokens"]), int(p["completion_tokens"]))
        for p in priced
    )
    return {
        "call_count": len(predictions),
        "unpriced_call_count": unpriced,
        "models": models,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": round(total, 6),
        "cost_usd_per_call": round(total / len(priced), 8) if priced else None,
        "price_source": PRICE_SOURCE,
        "price_checked_on": PRICE_CHECKED_ON,
    }


def record_predictions(
    dsn: str | None = None,
    pairs: list[tuple[str, str]] | None = None,
    max_workers: int = MAX_WORKERS,
    resume: bool = False,
) -> list[dict[str, Any]]:
    """The only function here that calls out. Produces `calibration_predictions.json` and
    `calibration_cost.json`.

    `pairs` exists so a small, defensible sample can be run and committed when the full run's
    extrapolated cost has not been approved — the harness is the same either way, and the
    committed cost file says how many calls it actually paid for.
    """
    from explorer.evals.extract_deal_point import predict

    if not settings.has_openai_key or settings.openai_api_key is None:
        raise SystemExit("calibration needs OPENAI_API_KEY.")
    api_key = settings.openai_api_key

    scheduled = pairs if pairs is not None else holdout_pairs(dsn)

    # A resumed run keeps what already landed and prices only what it adds, so the committed
    # cost is the cost of the table rather than of one attempt at it.
    already: list[dict[str, Any]] = []
    if resume and PREDICTIONS_FILE.is_file():
        already = json.loads(PREDICTIONS_FILE.read_text())
        scheduled = missing_pairs(scheduled, already)

    matter_ids = sorted({m for m, _ in scheduled})
    names = sorted({d for _, d in scheduled})

    with psycopg.connect(dsn or settings.database_url) as conn:
        source_rows = conn.execute(
            "SELECT id, source_file FROM matters WHERE id = ANY(%(ids)s)", {"ids": matter_ids}
        ).fetchall()
        # One query for every deal point's position vocabulary, instead of one per call as the
        # #28 version did — at 1,700 calls that was 1,700 round trips for 92 distinct answers.
        position_rows = conn.execute(
            "SELECT deal_point_name, position FROM deal_points "
            "WHERE deal_point_name = ANY(%(names)s)",
            {"names": names},
        ).fetchall()

    sources: dict[str, str] = dict(source_rows)
    allowed_by_point: dict[str, set[str]] = {}
    for name, position in position_rows:
        allowed_by_point.setdefault(name, set()).add(position)

    # `source_file` is recorded relative to `data/`, not the repo root (the same convention
    # `api/matters.py`'s DATA_ROOT follows) — joining it under the MAUD corpus root directly,
    # as an earlier version of this function did, silently produced zero matches.
    data_root = ROOT / "data"

    texts: dict[str, str] = {}
    for matter_id in matter_ids:
        source_file = sources.get(matter_id)
        if not source_file:
            continue
        path = data_root / source_file
        if not path.is_file():
            continue
        texts[matter_id] = path.read_text(encoding="utf-8", errors="replace")

    runnable = [(m, d) for m, d in scheduled if m in texts]

    def one(pair: tuple[str, str]) -> dict[str, Any] | None:
        """A call that will not come back is dropped, not faked.

        Over 1,700 calls a transient 429 is likely, and `pool.map` propagates the first
        exception — losing every prediction already paid for. Retrying briefly and then
        returning None keeps the run's cost from being spent twice; the dropped pair simply
        does not appear in the table's n, which is the honest way to be short of data.
        """
        matter_id, deal_point = pair
        allowed = sorted(allowed_by_point.get(deal_point, set()))
        for attempt in range(MAX_ATTEMPTS):
            try:
                return asdict(predict(matter_id, texts[matter_id], deal_point, allowed, api_key))
            except Exception as failure:  # noqa: BLE001 - any API failure is retried then dropped
                if attempt == MAX_ATTEMPTS - 1:
                    log.warning(
                        "calibration_prediction_dropped",
                        matter_id=matter_id,
                        deal_point_name=deal_point,
                        error=type(failure).__name__,
                    )
                    return None
                # Jittered exponential backoff. #44's first pass used three attempts at 1s and
                # 2s and lost 325 calls to rate limits: every worker retried in lockstep and hit
                # the same limit again. The jitter is what breaks the lockstep.
                time.sleep(2**attempt + random.random())
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fresh = [p for p in pool.map(one, runnable) if p is not None]

    predictions = already + fresh
    predictions.sort(key=lambda p: (p["matter_id"], p["deal_point_name"]))
    PREDICTIONS_FILE.write_text(json.dumps(predictions, indent=2) + "\n")

    cost = run_cost(predictions)
    cost["scheduled_pairs"] = len(scheduled) + len(already)
    cost["dropped_pairs"] = cost["scheduled_pairs"] - len(predictions)
    COST_FILE.write_text(json.dumps(cost, indent=2) + "\n")
    return predictions


def grade(
    predictions_path: Path = PREDICTIONS_FILE,
    dsn: str | None = None,
    vocabulary: list[str] | None = None,
) -> dict[str, Any]:
    """Offline: reads the committed predictions file and MAUD's own labels from the DB, no
    LLM call. Needs the corpus loaded, not a key.

    `vocabulary` widens the table to deal points the run never reached, so the report shows
    coverage rather than quietly reporting only what was measured. Default keeps the pre-#44
    behaviour of grading exactly what is in the file.
    """
    predictions = json.loads(predictions_path.read_text())
    matter_ids = sorted({p["matter_id"] for p in predictions})
    predicted_names = sorted({p["deal_point_name"] for p in predictions})
    names = sorted(set(vocabulary)) if vocabulary is not None else predicted_names
    actual = actual_positions(matter_ids, sorted(set(names) | set(predicted_names)))

    results: list[DealPointResult] = []
    for deal_point in names:
        rows = [p for p in predictions if p["deal_point_name"] == deal_point]
        n = len(rows)
        if n == 0:
            results.append(
                DealPointResult(
                    deal_point_name=deal_point,
                    n=0,
                    correct=0,
                    accuracy=None,
                    ci_low=None,
                    ci_high=None,
                    reportable=False,
                    measured=False,
                )
            )
            continue
        correct = sum(
            1 for p in rows if actual.get((p["matter_id"], deal_point)) == p["predicted_position"]
        )
        ci_low, ci_high = wilson_interval(correct, n)
        results.append(
            DealPointResult(
                deal_point_name=deal_point,
                n=n,
                correct=correct,
                accuracy=round(correct / n, 3),
                ci_low=round(ci_low, 3),
                ci_high=round(ci_high, 3),
                # The lower bound, not the point estimate: 3 of 4 correct is 0.75 but its CI
                # reaches 0.30, and a deal point cannot be flattered into reportability by a
                # sample too small to distinguish it from a coin flip.
                reportable=ci_low >= settings.min_extraction_confidence,
                measured=True,
            )
        )

    # Worst first — the weakness map is the point of the table — with unmeasured rows last,
    # since they are a coverage fact rather than an accuracy fact.
    results.sort(key=lambda r: (not r.measured, r.accuracy if r.accuracy is not None else 0.0))

    measured = [r for r in results if r.measured]
    return {
        "vocabulary_size": len(results),
        "deal_point_count": len(results),
        "measured_deal_point_count": len(measured),
        "reportable_count": sum(1 for r in measured if r.reportable),
        "prediction_count": len(predictions),
        "min_extraction_confidence": settings.min_extraction_confidence,
        "cost": run_cost(predictions),
        "results": results,
    }


def write_accuracy_table(summary: dict[str, Any]) -> Path:
    """The machine-readable table `confidence_lookup()` and the Admin view both read, so the
    number in the UI and the number in the gate cannot drift apart."""
    payload = {
        key: value for key, value in summary.items() if key not in {"results", "deal_point_count"}
    }
    payload["results"] = [asdict(r) for r in summary["results"]]
    ACCURACY_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    return ACCURACY_FILE


if __name__ == "__main__":
    summary = grade(vocabulary=deal_point_vocabulary())
    for r in summary["results"]:
        print(r)
    print({k: v for k, v in summary.items() if k != "results"})
    print("wrote", write_accuracy_table(summary))
