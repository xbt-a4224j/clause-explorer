# Merge notes — #53 (drop the retrieval ablation)

`README.md` was **not edited** by this branch, per the working constraint on the issue. This
file records what a reviewer should change there before or after merge.

## README passages that mention the ablation

**None.** `README.md` never names the retrieval ablation, `retrieval-ablation.md`,
`retrieval_ablation`, `retrieval_set`, MRR, recall@k, or any of the numbers the ablation
produced. Grepped for all of them:

```
$ grep -niE "ablation|mrr|reciprocal|recall@|0\.785|0\.744|retrieval_set|pure vector" README.md
(no matches)
```

So nothing in the README is now *wrong*. Two lines are mildly stale in wording and worth a
one-line touch by whoever owns the README:

| Line | Current text | Why it is now imprecise |
|---|---|---|
| 210 | `make eval     # eval + calibration harnesses; writes docs/results/` | "eval + calibration" described three harnesses. Two remain: calibration and measure-selection. The `Makefile` comment was updated to `calibration + measure-selection harnesses`; this line is the copy of it. |
| 96 | `... ingest status, the calibration tables, eval results, and live structured logs.` | Still accurate — `/admin/evals` now returns only the measure-selection report. No change strictly needed. |

## Documents this branch **did** change

* `docs/demo-scripts.md`, Script 1 Beat 3. It quoted the ablation directly — "hybrid beats
  pure vector 0.785 to 0.744 on mean reciprocal rank". That number no longer has a command
  behind it, which the project's no-fabricated-numbers rule forbids. Replaced with the claim
  the code still supports: both score distributions are min-max normalised per query before
  blending, asserted by `backend/tests/test_hybrid_retrieval.py`, and an explicit
  "which method wins is not measured".

## Also worth a reviewer's eye

* `backend/explorer/retrieval/warm_cache.py` gained `ranking_probe_texts()`. It is the query
  generation that lived in the deleted `evals/retrieval_set.py`, minus the relevance
  judgements and the `EvalQuery` dataclass. It had to move rather than die: the committed
  `data/embeddings/vectors.npz` is under version control, `/comparables` free-text ranking is
  only exercisable with no API key against cached text, and `warm_cache` is the only writer of
  that file. The wording and the sampling are reproduced **unchanged** so a re-run adds
  nothing. Verified: all 90 probe texts resolve to vectors already in the committed cache.
* `#49` is editing `evals/retrieval_set.py` for a label lookup. This branch deletes that file
  outright, so there is no textual conflict to resolve — but whoever merges second needs to
  decide where #49's label lookup lands now that its host file is gone.
