"""`python -m explorer.evals` — run the eval harnesses from one command.

    PYTHONPATH=backend python -m explorer.evals --all --out docs/results

Two harnesses, and both point at the model rather than at the plumbing:

* **calibration** — the extractor against held-out MAUD labels, per deal point with its own n
* **measure-selection** — the agent's Cube selection against the authored eval set

Both grade artefacts that are already committed, so neither makes an LLM call and neither needs
`OPENAI_API_KEY`; calibration reads the corpus and the review queue, so it needs the database.

What this deliberately does **not** write: the narrative reports in `docs/results/*.md`. Those
are prose authored around numbers a run produced, including the caveats — regenerating them
from a template would delete the commentary, which is the part worth reading.

A third harness lived here until #53: the BM25/vector/hybrid retrieval ablation. It was removed
because two of its three query phrasings saturated, so it measured a task nothing could fail.
What defends the retrieval design now is a test, not an eval —
`backend/tests/test_hybrid_retrieval.py` asserts both score distributions are min-max
normalised per query before they are blended.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from explorer.evals import calibration, measure_selection

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "docs" / "results"


def run_calibration(out: Path) -> None:
    """Grade once, write both artefacts from the same numbers.

    Two `grade()` calls would hit the database twice and could, if a reviewer labelled
    something in between, write two files that disagree.
    """
    summary = calibration.grade(vocabulary=calibration.deal_point_vocabulary())
    print({key: value for key, value in summary.items() if key != "results"})
    print("wrote", calibration.write_accuracy_table(summary))
    labels_path = out / calibration.LABEL_RESULTS_FILE.name
    labels = calibration.write_report(summary, out_path=labels_path)
    print("wrote", labels_path)
    print(
        f"correct {labels['correct_before']} of {labels['prediction_count']} before, "
        f"{labels['correct_after']} of {labels['prediction_count']} after; "
        f"{labels['labels_applied']} labels applied, {labels['labels_differing']} differing"
    )


def run_measure_selection(out: Path) -> None:
    """Pure and offline — both inputs are committed files.

    It used to write nothing, on the grounds that a deterministic grade over committed inputs
    is reproducible on demand. #54 needed the scores on a chart, and "reproducible on demand"
    turns into "recomputed per request", which can drift from the report committed beside it.
    So the aggregate is written as JSON too, next to the markdown it already produced.
    """
    summary = measure_selection.run()
    print({key: value for key, value in summary.items() if key != "results"})
    print("wrote", measure_selection.write_summary(summary))


HARNESSES: dict[str, Callable[[Path], None]] = {
    "calibration": run_calibration,
    "measure-selection": run_measure_selection,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m explorer.evals",
        description="Run the eval harnesses and write their machine-readable output.",
    )
    parser.add_argument("--all", action="store_true", help="run every harness")
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(HARNESSES),
        metavar="HARNESS",
        help=f"run one harness; repeatable. One of: {', '.join(sorted(HARNESSES))}",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"directory for generated artefacts (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()

    selected = sorted(HARNESSES) if args.all else (args.only or [])
    if not selected:
        parser.error("nothing to run: pass --all, or --only <harness>")

    args.out.mkdir(parents=True, exist_ok=True)
    for name in selected:
        print(f"== {name} ==")
        HARNESSES[name](args.out)


if __name__ == "__main__":
    main()
