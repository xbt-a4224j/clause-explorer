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
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

from explorer.api.logging import get_logger
from explorer.api.settings import settings
from explorer.evals.context import PassageIndex, retrieval_query
from explorer.evals.fewshot import Example, select_examples
from explorer.evals.pricing import PRICE_CHECKED_ON, PRICE_SOURCE, cost_usd
from explorer.retrieval.embeddings import EMBED_MODEL, EmbeddingCache

log = get_logger()

ROOT = Path(__file__).resolve().parents[3]
SPLIT_FILE = ROOT / "docs" / "eval" / "calibration_split.json"
PREDICTIONS_FILE = ROOT / "docs" / "eval" / "calibration_predictions.json"
# committed; the Admin tab reads this rather than recomputing (#41)
LABEL_RESULTS_FILE = ROOT / "docs" / "results" / "calibration-labels.json"
COST_FILE = ROOT / "docs" / "eval" / "calibration_cost.json"
ACCURACY_FILE = ROOT / "docs" / "eval" / "calibration_accuracy.json"

# The #44 run, kept as the control (#58). It is not deleted and not superseded: it is the
# measurement of the same extractor shown the first 12,000 characters instead of the retrieved
# ones, and the pair is only informative side by side.
PREFIX_PREDICTIONS_FILE = ROOT / "docs" / "eval" / "calibration_predictions_prefix.json"
PREFIX_COST_FILE = ROOT / "docs" / "eval" / "calibration_cost_prefix.json"
PREFIX_ACCURACY_FILE = ROOT / "docs" / "eval" / "calibration_accuracy_prefix.json"

# "prefix" is #44's `contract_text[:12000]`; "retrieval" is #58's hybrid-retrieved passages in
# the same 12,000-character budget. Both run through the same harness, which is the only way
# the two numbers are comparable.
PREFIX_MODE = "prefix"
RETRIEVAL_MODE = "retrieval"

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
    """`accuracy` is the graded number — the one #23's `reportable` gate reads. `*_before` is
    the same number with human labels excluded, kept alongside so the Admin table can show what
    the review queue actually moved instead of asserting that it moved something (#41).

    `measured` separates a deal point the run never reached from one it got wrong (#44)."""

    deal_point_name: str
    n: int
    correct: int
    # None, not 0.0, when nothing was measured. "We got none right" and "we never asked" are
    # different findings and must not render alike.
    accuracy: float | None
    ci_low: float | None
    ci_high: float | None
    reportable: bool
    # `accuracy_before` is `| None` for the same reason `accuracy` is: an unmeasured deal point
    # has no before-number either.
    correct_before: int
    accuracy_before: float | None
    labels_applied: int
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
    vocabulary: list[str] | None = None,
) -> dict[str, Any]:
    """Grade predictions against gold, preferring a human label over the model's answer for the
    same (matter_id, deal_point_name) (#41), across the whole deal-point vocabulary (#44).

    Pure: no database, no key, no files — which is what makes the substitution rule testable at
    all. The rule is a *substitution*, not a correction: a label replaces the prediction and is
    then graded like any other answer, so a mistyped label lowers the score. Anything else would
    make the loop a ratchet that can only report improvement.

    `vocabulary` widens the table to deal points the run never reached, so the report shows
    coverage rather than quietly reporting only what was measured. Default grades exactly what
    is in the predictions file.
    """
    predicted_names = sorted({p["deal_point_name"] for p in predictions})
    names = sorted(set(vocabulary)) if vocabulary is not None else predicted_names

    results: list[DealPointResult] = []
    labels_applied = 0
    labels_differing = 0
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
                    correct_before=0,
                    accuracy_before=None,
                    labels_applied=0,
                    measured=False,
                )
            )
            continue
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
                correct_before=correct_before,
                accuracy_before=round(correct_before / n, 3),
                labels_applied=applied,
                measured=True,
            )
        )

    # Worst first — the weakness map is the point of the table — with unmeasured rows last,
    # since they are a coverage fact rather than an accuracy fact.
    results.sort(key=lambda r: (not r.measured, r.accuracy if r.accuracy is not None else 0.0))

    measured = [r for r in results if r.measured]
    total = sum(r.n for r in results)
    return {
        "vocabulary_size": len(results),
        "deal_point_count": len(results),
        "measured_deal_point_count": len(measured),
        "reportable_count": sum(1 for r in measured if r.reportable),
        "prediction_count": len(predictions),
        "total_tokens": sum(int(p["tokens"]) for p in predictions),
        "min_extraction_confidence": settings.min_extraction_confidence,
        "cost": run_cost(predictions),
        "labels_applied": labels_applied,
        "labels_differing": labels_differing,
        "correct_before": sum(r.correct_before for r in results),
        "correct_after": sum(r.correct for r in results),
        "accuracy_before": (sum(r.correct_before for r in results) / total) if total else 0.0,
        "accuracy_after": (sum(r.correct for r in results) / total) if total else 0.0,
        "results": results,
    }


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


def build_passage_index(text: str, cache: EmbeddingCache) -> PassageIndex:
    """One matter's retrieval index, retried through the embedding rate limit (#58).

    Embedding a single holdout agreement's passages is ~226,000 tokens. Twenty of them
    back-to-back exceeded the org's 1,000,000 tokens-per-minute embedding limit and the first
    full retrieval attempt died with a 429 after building four indexes — the same failure the
    extraction loop already survives, in the one place that had no wrapper for it.

    Retrying is cheap because `EmbeddingCache` keeps what already landed in memory: a second
    attempt re-requests only the batch that failed, not the whole document.

    Unlike a dropped prediction, a failure here is raised rather than swallowed. An index that
    is missing or empty would send the model an empty contract and the run would report an
    accuracy for a question nobody was asked.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            return PassageIndex(text, cache=cache)
        except Exception as failure:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            log.warning(
                "calibration_index_retry",
                attempt=attempt + 1,
                error=type(failure).__name__,
            )
            time.sleep(2**attempt + random.random())
    raise RuntimeError("unreachable: the loop above either returns or raises")


def record_predictions(
    dsn: str | None = None,
    pairs: list[tuple[str, str]] | None = None,
    max_workers: int = MAX_WORKERS,
    resume: bool = False,
    mode: str = RETRIEVAL_MODE,
    predictions_file: Path = PREDICTIONS_FILE,
    cost_file: Path = COST_FILE,
) -> list[dict[str, Any]]:
    """The only function here that calls out. Produces `calibration_predictions.json` and
    `calibration_cost.json`.

    `pairs` exists so a small, defensible sample can be run and committed when the full run's
    extrapolated cost has not been approved — the harness is the same either way, and the
    committed cost file says how many calls it actually paid for.

    `mode` selects what the model is shown (#58). `RETRIEVAL_MODE` retrieves passages for the
    deal point and adds MAUD few-shot examples from held-in matters; `PREFIX_MODE` reproduces
    the #44 control exactly — the first 12,000 characters, zero-shot. Both write through the
    same code, so the before/after pair compares two runs rather than a run and a memory.
    """
    from explorer.evals.extract_deal_point import predict

    if not settings.has_openai_key or settings.openai_api_key is None:
        raise SystemExit("calibration needs OPENAI_API_KEY.")
    api_key = settings.openai_api_key

    scheduled = pairs if pairs is not None else holdout_pairs(dsn)

    # A resumed run keeps what already landed and prices only what it adds, so the committed
    # cost is the cost of the table rather than of one attempt at it.
    already: list[dict[str, Any]] = []
    if resume and predictions_file.is_file():
        already = json.loads(predictions_file.read_text())
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

    # #58. Both of these are built before the thread pool starts, deliberately:
    #
    # * one `PassageIndex` per matter, reused across that matter's ~90 deal points, because
    #   rebuilding it per call would re-embed several hundred passages for identical vectors;
    # * every query embedded once, up front, because `EmbeddingCache` is a plain dict and eight
    #   workers arriving at the same uncached query would each pay for it.
    examples_by_point: dict[str, list[Example]] = {}
    indexes: dict[str, PassageIndex] = {}
    queries: dict[str, str] = {}
    cache = EmbeddingCache(api_key=api_key)
    if mode == RETRIEVAL_MODE:
        holdout = json.loads(SPLIT_FILE.read_text())["holdout_matter_ids"]
        examples_by_point = select_examples(names, holdout, data_root=data_root, dsn=dsn)
        log.info(
            "calibration_examples_selected",
            deal_points=len(names),
            with_examples=sum(1 for v in examples_by_point.values() if v),
            examples=sum(len(v) for v in examples_by_point.values()),
        )
        queries = {
            name: retrieval_query(name, sorted(allowed_by_point.get(name, set()))) for name in names
        }
        cache.embed_many(sorted(set(queries.values())))
        for matter_id in sorted({m for m, _ in runnable}):
            started = time.time()
            indexes[matter_id] = build_passage_index(texts[matter_id], cache=cache)
            log.info(
                "calibration_index_built",
                matter_id=matter_id,
                chars=len(texts[matter_id]),
                passages=len(indexes[matter_id].passages),
                seconds=round(time.time() - started, 2),
            )

    def one(pair: tuple[str, str]) -> dict[str, Any] | None:
        """A call that will not come back is dropped, not faked.

        Over 1,700 calls a transient 429 is likely, and `pool.map` propagates the first
        exception — losing every prediction already paid for. Retrying briefly and then
        returning None keeps the run's cost from being spent twice; the dropped pair simply
        does not appear in the table's n, which is the honest way to be short of data.
        """
        matter_id, deal_point = pair
        allowed = sorted(allowed_by_point.get(deal_point, set()))
        passages = (
            indexes[matter_id].search(queries[deal_point]) if mode == RETRIEVAL_MODE else None
        )
        examples = examples_by_point.get(deal_point, [])
        for attempt in range(MAX_ATTEMPTS):
            try:
                return asdict(
                    predict(
                        matter_id,
                        texts[matter_id],
                        deal_point,
                        allowed,
                        api_key,
                        passages=passages,
                        examples=examples,
                        context_mode=mode,
                    )
                )
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
    predictions_file.write_text(json.dumps(predictions, indent=2) + "\n")

    cost = run_cost(predictions)
    cost["scheduled_pairs"] = len(scheduled) + len(already)
    cost["dropped_pairs"] = cost["scheduled_pairs"] - len(predictions)
    cost["context_mode"] = mode
    # Retrieval is not free: every passage of every holdout agreement is embedded once. The
    # token count is measured by the cache, and it is recorded next to the extraction cost
    # rather than folded into it, because they are different models at different prices.
    cost["embedding_model"] = EMBED_MODEL
    cost["embedding_api_calls"] = cache.api_calls
    cost["embedding_tokens"] = cache.api_tokens
    cost_file.write_text(json.dumps(cost, indent=2) + "\n")
    return predictions


def grade(
    predictions_path: Path = PREDICTIONS_FILE,
    dsn: str | None = None,
    use_labels: bool = True,
    vocabulary: list[str] | None = None,
) -> dict[str, Any]:
    """Offline: reads the committed predictions file, MAUD's own labels from `deal_points`, and
    the review queue's decisions from `labels`. No LLM call. Needs the corpus loaded, not a key.

    `use_labels=False` grades the extractor alone — the same number this function returned
    before #41, kept as a switch so "what did the humans change" is answerable by running the
    same code twice rather than by trusting a stored column.

    `vocabulary` widens the table to deal points the run never reached, so the report shows
    coverage rather than quietly reporting only what was measured (#44). Default keeps the
    pre-#44 behaviour of grading exactly what is in the file.
    """
    predictions = json.loads(predictions_path.read_text())
    matter_ids = sorted({p["matter_id"] for p in predictions})
    predicted_names = sorted({p["deal_point_name"] for p in predictions})
    names = sorted(set(vocabulary)) if vocabulary is not None else predicted_names
    actual = actual_positions(matter_ids, sorted(set(names) | set(predicted_names)))
    keys = [(p["matter_id"], p["deal_point_name"]) for p in predictions]
    labels = human_labels(keys, dsn=dsn) if use_labels else {}
    return score(predictions, actual, labels, vocabulary=vocabulary)


def write_report(
    summary: dict[str, Any] | None = None,
    predictions_path: Path = PREDICTIONS_FILE,
    out_path: Path = LABEL_RESULTS_FILE,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Write the committed before/after artefact the Admin tab reads (#41).

    Admin renders a file rather than recomputing, for the reason the markdown report already
    gives: a number the UI computes on its own can drift from the number a reviewer reads in
    the repo, and then there are two.

    `summary` is accepted so the CLI can grade once and write both artefacts from the same
    numbers. Two `grade()` calls would hit the database twice and could, if a reviewer labelled
    something between them, write two files that disagree.
    """
    if summary is None:
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
        # Measured rows only. An unmeasured deal point has no before and no after; listing it
        # here with zeros would read as "the reviewers changed nothing on it", which is a
        # different claim from "nobody measured it".
        "results": [asdict(r) for r in summary["results"] if r.measured],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def write_accuracy_table(summary: dict[str, Any], out_path: Path = ACCURACY_FILE) -> Path:
    """The machine-readable table `confidence_lookup()` and the Admin view both read, so the
    number in the UI and the number in the gate cannot drift apart.

    `out_path` is a parameter so the prefix control's table can be written beside the retrieval
    one (#58). Only the default path is read by the app; the control is there to be compared
    against, not to be served.
    """
    payload = {
        key: value for key, value in summary.items() if key not in {"results", "deal_point_count"}
    }
    payload["results"] = [asdict(r) for r in summary["results"]]
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


if __name__ == "__main__":
    summary = grade(vocabulary=deal_point_vocabulary())
    for r in summary["results"]:
        print(r)
    print({k: v for k, v in summary.items() if k != "results"})
    print("wrote", write_accuracy_table(summary))
    labels = write_report(summary)
    print("wrote", LABEL_RESULTS_FILE)
    print(
        f"correct {labels['correct_before']} of {labels['prediction_count']} before, "
        f"{labels['correct_after']} of {labels['prediction_count']} after; "
        f"{labels['labels_applied']} labels applied, {labels['labels_differing']} differing"
    )
