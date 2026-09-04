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
