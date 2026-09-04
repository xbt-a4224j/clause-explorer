# Merge notes for #44 — README passages that need updating

This branch does **not** touch `README.md`; another process owns it. Everything below is a
change that branch should make. Every figure comes from
`docs/eval/calibration_accuracy.json` and `docs/eval/calibration_cost.json`, both committed on
this branch, and is written up in `docs/results/calibration.md`.

Delete this file once the README is updated.

---

## 1. Limitations — replace the "4 of 5" bullet

**Current text** (README.md, Limitations list, last bullet):

> - **The extractor is mostly below its own gate.** Of 5 calibrated deal points, 4 are under 0.7
>   accuracy (0.50, 0.30, 0.30, 0.20; one at 0.95). Published so it is clear which questions the
>   system must decline on un-annotated documents.

**Replace with:**

> - **The extractor is below its own gate almost everywhere.** All 92 deal points are now
>   calibrated against held-out MAUD labels: 90 are measurable on the 20-matter holdout, and
>   **5 of those 90 clear the 0.70 gate** on the lower bound of their 95% CI. 77 of 90 are below
>   0.70 on the point estimate, the median accuracy is 0.25, and 6 deal points score 0.000. The
>   5 that clear are near-binary questions answered by boilerplate stated early in an agreement;
>   what fails is everything needing the graded judgment MAUD's own annotators were trained for.
>   The 2 unmeasured deal points are a coverage gap — MAUD answers them on no holdout matter —
>   and are reported as "not measured", never as zero. Full table:
>   [`docs/results/calibration.md`](docs/results/calibration.md).

Why the wording changed beyond the numbers: "4 of 5" described a hand-picked slice chosen for
being easy to grade. The honest headline is now the ratio over the whole vocabulary.

## 2. Limitations — the Label loop bullet

**Current text:**

> - **The Label loop does not close.** Decisions write to `labels`; calibration does not read them.
>   On this corpus it could not usefully: every queued item already has a lawyer's answer.

Still true, keep it. Add the queue size, which the README states nowhere:

> The queue now draws from the full prediction set — **1,701 items across 90 deal points**, up
> from 100 across 5.

## 3. Optional: the cost figure is now publishable

The README has no cost line. If one is wanted, this is the measured figure:
the full calibration run cost **$0.854442** — 1,701 calls, 5,440,750 input and 63,882 output
tokens on `gpt-4o-mini`, priced from the vendor page read 2026-09-03. Not a range: #28 could
only bound its cost because it recorded total tokens, and output costs 4x input.

## 4. Nothing else changes

Architecture, Data, "Why it refuses to answer sometimes", and the semantic-layer sections are
unaffected by this branch.

---

## Overlap with #41 (`worktree-agent-ad29e51e1d6b7b79e`, commit d26cbdd)

#41 and #44 both rewrite `calibration.py`, `docs/results/calibration.md`, and the Admin
calibration area. They are compatible in intent — #41 changes *whose answer* is graded, #44
changes *how many* deal points are graded — but they cannot be merged textually. The overlaps,
in the order they matter:

1. **`docs/results/calibration-labels.json` is stale after this branch.** It records
   `prediction_count: 100`, `correct_before: 45`, `correct_after: 44` against #28's 100
   predictions. This branch replaces `calibration_predictions.json` with 1,701 predictions
   from a changed answer channel, so those numbers no longer describe anything on disk.
   **Regenerate it after the merge**; do not hand-edit the figures. #41's own unit tests for
   `score()` are fixture-based and will still pass, so nothing will fail loudly to warn you.
2. **`DealPointResult`.** #41 adds `correct_before`, `accuracy_before`, `labels_applied`.
   #44 makes `accuracy`, `ci_low`, `ci_high` `float | None` and adds `measured: bool`, so an
   unmeasured deal point is not reported as 0.00. Both sets of fields should survive; the
   `| None` change has to propagate to #41's `*_before` fields for the same reason.
3. **`grade()`.** #41 splits the pure part into `score()` and prefers a human label over the
   prediction. #44 adds a `vocabulary` argument, emits a row per deal point in the whole
   vocabulary, sorts worst-first, and attaches the run cost. The label substitution belongs
   *inside* #44's per-deal-point loop, before the correct/incorrect comparison.
4. **`DEAL_POINTS`.** #44 deletes the hardcoded five; #41 still imports them. The replacement
   is `deal_point_vocabulary()` plus `holdout_pairs()`.
5. **Admin.** #41 adds a labels section; #44 replaces `CalibrationReport` with a 92-row table.
   Independent components, one file — keep both.
6. **`docs/results/calibration.md`.** Take #44's structure and fold #41's before/after section
   into it once the regenerated label numbers exist.
