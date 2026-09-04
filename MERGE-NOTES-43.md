# Merge notes for #43 — README passages another process owns

`README.md` was not touched by this branch. Two passages in it are now incomplete, and one
number in it should be joined by the measured hit rate. Everything below is measured by
`PYTHONPATH=backend python -m explorer.evals.span_anchoring`, whose output is committed at
`docs/results/span-anchoring.md`.

## 1. Limitations — the "Most recorded spans are not clauses" bullet (README.md:151-155)

Current text:

> - **Most recorded spans are not clauses.** Over the 12,442 deal points with a span, the median
>   width is 4,658 characters and the 90th percentile is 238,949. MAUD marks where an answer was
>   found, and for a holistic deal point that is most of the agreement. Spans wider than 6,000
>   characters render as a labelled excerpt, not as the clause. A further 495 deal points (3.8%)
>   have no span at all and store NULL rather than a nearest guess.

Every figure in it still holds — the ingest re-run confirms median 4,658, p90 238,949, and 495
NULL spans. What it now omits is that we tried to fix it and measured how far that got. Suggested
replacement:

> - **Most recorded spans are not clauses, and anchoring did not change that.** Over the 12,442
>   deal points with a span, the median width is 4,658 characters and the 90th percentile is
>   238,949. Ingest now tries to locate each annotation's own quoted text inside its recorded
>   span and stores `span_kind = 'anchored'` where it is found exactly once: **7,476 of 12,937
>   deal points, 57.8%** (`docs/results/span-anchoring.md`). All 7,476 landed on a span
>   byte-identical to the one they replaced — where MAUD quotes one continuous passage the
>   locator already bounded exactly that passage, and where it quotes several (36.8% of rows,
>   joined by `<omitted>`) the width belongs to the annotation, not to our matching. So the
>   remaining 4,966 spans keep `span_kind = 'recorded'`, and anything wider than 6,000
>   characters still renders as a labelled excerpt rather than as the clause. A further 495 deal
>   points (3.8%) have no span at all; searching those against the whole document recovered
>   **0**, and they still store NULL rather than a nearest guess.

Two rules that should survive any rewording, because they are the point of the ticket: an excerpt
found more than once in its span is a **miss**, never a guess (0 rows hit that case in this
corpus, but the guard is tested); and no offset is ever approximated.

## 2. The drill-through screenshot caption (README.md:33-38)

The caption is still accurate — that matter's span is a `recorded` one and still renders as a
bounded excerpt. If the caption is ever reworded, the useful addition is that the span shown is
now labelled in the data as well as in the UI: `deal_points.span_kind` distinguishes a span that
*is* the quoted answer text from one that merely *contains* it.

## 3. Anything that enumerates `deal_points` columns

`deal_points` gained a nullable `span_kind TEXT` column (`'anchored' | 'recorded' | NULL`) with a
`NOT VALID` check constraint tying it to the presence of a span. If the README lists the schema
anywhere, that column belongs in the list.

## Not changed, deliberately

`slice_source` and the drill-through render exactly as before; `span_kind` is not exposed through
the API or Cube. No README passage about the drill-through's behaviour needs editing.

`frontend/src/views/DealTerms.tsx:217` repeats the same two span figures in its explainer prose.
They are still correct after the re-ingest — anchoring changed no span's width — so that copy was
left alone. Verified against the running API on the isolated database: for `contract_0`, 54
anchored rows served full clause text and 24 wide `recorded` rows served the 1,200-character
labelled excerpt, exactly as before this change.
