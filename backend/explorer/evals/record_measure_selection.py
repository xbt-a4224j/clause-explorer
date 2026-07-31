"""Records real agent output for every case in `docs/eval/measure_selection.json` (#27).

Run once, with a key, to produce `docs/eval/recorded_outputs.json` — a committed artefact the
offline harness (`measure_selection.py`) grades with no network. Re-run only when the eval set
or the model prompt changes; the graded numbers in `docs/results/measure-selection.md` are
computed from the committed recording, not regenerated on every CI run.

    PYTHONPATH=backend python -m explorer.evals.record_measure_selection
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVAL_SET = ROOT / "docs" / "eval" / "measure_selection.json"
RECORDED = ROOT / "docs" / "eval" / "recorded_outputs.json"


def main() -> None:
    from explorer.agent.select import fetch_vocabulary, select_via_llm
    from explorer.api.settings import settings

    if not settings.has_openai_key or settings.openai_api_key is None:
        raise SystemExit("record_measure_selection needs OPENAI_API_KEY.")
    api_key = settings.openai_api_key

    cases = json.loads(EVAL_SET.read_text())
    vocabulary = fetch_vocabulary()

    recorded = []
    for case in cases:
        try:
            selection = select_via_llm(case["question"], vocabulary, api_key)
        except Exception as exc:  # noqa: BLE001 - record the failure, do not stop the run
            selection = {"error": str(exc)}
        recorded.append({"id": case["id"], "question": case["question"], "output": selection})
        print(f"{case['id']}: {selection}", file=sys.stderr)

    RECORDED.write_text(json.dumps(recorded, indent=2) + "\n")
    print(f"wrote {len(recorded)} recorded outputs to {RECORDED}")


if __name__ == "__main__":
    main()
