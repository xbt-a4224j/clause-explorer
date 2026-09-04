# MERGE-NOTES-45 — README passages made wrong by #45

Issue #45 was implemented without touching `README.md`, because another process owns that file.
This is the list of passages that are now false, and what each should say. Line numbers are
against `README.md` as of commit `9c83106`.

## 1. Line 94 — Admin no longer has an architecture diagram

Current:

> | **Tables / Admin** | Browsable raw data, ingest status, the calibration table, an architecture diagram, and live structured logs. |

`ArchitectureDiagram.tsx` was deleted. It was a second whole-system drawing; `SystemDiagram` on
Overview is now the only one, so a reader cannot find two pictures of the same system and go
hunting for the difference between them. Admin keeps ingest status, calibration, eval results
and the log viewer.

Should say:

> | **Tables / Admin** | Browsable raw data, ingest status, the calibration table, eval results, and live structured logs. |

Nothing else in the README claims an architecture diagram, and the whole-system picture is still
described accurately by the ASCII diagram in `CLAUDE.md`.

## 2. Screenshots are stale — `docs/img/overview.png` in particular

`README.md` line 6 embeds `docs/img/overview.png`, and line ~178 promises the screenshots cannot
drift:

> The annotated screenshots in this README are generated, not captured by hand:
> `cd frontend && node scripts/shots.mjs` re-shoots the whole set against a running app…

That claim is still *true as a mechanism* — no callout selector used by `shots.mjs` was removed,
so the script will still run and locate every callout. But the pages it shoots have changed:

- **`overview.png`** — three prose sections were cut from Overview (the hybrid-retrieval
  section entirely, plus "The other four tabs"), and the surviving prose was shortened. The
  page is materially shorter than the committed shot.
- **`explore.png`, `deal-terms.png`, `coverage.png`, `label.png`, `refusal.png`** — the
  explainer panels are collapsed in every shot (`shots.mjs` collapses them deliberately), so
  these should be unchanged apart from any reflow.

**`node scripts/shots.mjs` was NOT run** — see "Not done" below. Whoever merges should re-shoot
at least `overview.png` against a running stack before the README's "cannot silently drift"
sentence is true again.

## 3. Nothing else in the README describes anything removed

Checked by grep and found clean:

- The README never mentions `POST /agent/select` or `POST /agent/resolve-filter-value` (the two
  deleted routes). It describes the semantic-layer *argument* at lines ~110–124, which is still
  accurate: `/agent/run-selection`, `/agent/catalog` and `/agent/grading` all still exist and
  are what the Semantic Layer tab uses.
- The README never links `docs/DESIGN.md`, so replacing that file with a short note pointing at
  `frontend/src/styles/tokens.css` breaks no README link.
- The README never links `docs/ownership-tasks.html`, which was removed.
- The README never names the three deleted Cube members (`has_source_span`, `with_industry_n`,
  `with_signing_date_n`) or any deleted CSS selector.
- `docs/walkthrough.md` is linked at line 176 and still exists; it grew a new final section,
  "Why it is built this way", holding the argument cut out of the UI. The README's one-line
  description of it ("Worked examples with real observed output from the running stack") is now
  incomplete rather than wrong — optionally extend it to mention the appendix.

## Not done, and why

- **`node scripts/shots.mjs` was not run.** It needs a running `docker compose` stack, and the
  Postgres on `localhost:5432` is shared with other agents working in parallel. Booting the app
  against it to take screenshots was out of scope for a frontend/docs change, so the committed
  images are stale by the amount described in §2.
