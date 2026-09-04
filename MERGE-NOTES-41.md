# Merge notes — #41, closing the Label loop

I did not edit `README.md`; another process owns it. These are the passages #41 makes wrong, and
what they should say instead. Line numbers are against `README.md` as of commit `9c83106`.

## 1. Limitations — the Label-loop entry must come out entirely

**Lines 161–162, delete both lines of the bullet:**

> - **The Label loop does not close.** Decisions write to `labels`; calibration does not read them.
>   On this corpus it could not usefully: every queued item already has a lawyer's answer.

The first sentence is now false and the bullet goes. The *second* sentence is still true and must
not be lost with it — move it into the Label row of the tab table (item 4), where it now belongs.

It closes now. `backend/explorer/evals/calibration.py:score()` prefers the latest `labels` row over
the model's prediction for the same `(matter_id, deal_point_name)` and grades it against MAUD like
any other answer. Nothing replaces this bullet — it is no longer a limitation. Do **not** substitute
a softer version of it ("the loop closes but only shallowly"): the loop closes, and the honest
qualification is a different claim, covered in item 4 below.

## 2. Journey 3 is no longer "half built"

**Line 59, currently:**

> queues the disagreements. This journey is **half built**, and the tab says so on screen.

**Should say** something to the effect of:

> queues the disagreements, and the next calibration run grades your decisions in place of the
> model's — the accuracy table on Admin moves.

The words "half built" no longer appear anywhere in the app; `frontend/src/journeys.ts` sets
journey 3's `limit` to `null`, and the Overview card names `Admin · the number moves` as its last
step. A README that still says "the tab says so on screen" is asserting something the screen
contradicts.

## 3. The italic caption under journey 3

**Line 65, currently ends:**

> *…calibrated confidence score exists. Decisions are recorded; calibration does not read them back yet.*

**The last sentence should be replaced with** something like:

> *Decisions are recorded, and calibration reads them back: a decision replaces the model's answer
> on the next grading run, so a mistyped label moves the accuracy table down.*

The "not a ratchet" half matters. The substitution is not a correction — a wrong label lowers the
score, and the committed run demonstrates exactly that (see item 5).

## 4. The tab table's Label row

**Line 95, currently:**

> | **Label** | A review queue ranked by disagreement between two extractors. Honest caveat: nothing reads its output yet — see Limitations. |

**Should say** something like:

> | **Label** | A review queue ranked by disagreement between two extractors. Decisions feed the next calibration run. Honest caveat: every queued item is a held-out matter that already has a lawyer's answer, so reviewing it teaches the system nothing gold did not — the mechanism earns its keep on un-annotated documents. |

**Keep the caveat, change what it says.** The old caveat ("nothing reads its output") is now false.
The one that replaces it is still true and still unflattering, and it is the sentence that must
survive: the loop closing means calibration *can* prefer a human label; it does not mean this
corpus needs one. That exact framing is now on the Label tab and in the Admin section, and the
README should not be the one surface that quietly drops it.

## 5. New artefact worth citing

`docs/results/calibration-labels.json` is committed and rendered by the Admin tab. The run behind
it (`docs/results/calibration.md`, new section "Human labels are read back into this score (#41)")
recorded, against the 6 decisions already sitting in `labels`: **45 of 100 correct before, 44 of 100
after, 6 labels applied, 2 of them differing from the model's answer.** The number went *down*,
because one recorded label is a stray `s` keystroke that turned a right answer wrong. If the README
gains a results reference, that is the number, and the decrease is the point rather than an
embarrassment to round away.

---

# Unrelated collision worth knowing about

This worktree was shared with another agent removing CUAD from the repo, and a `git stash` race
briefly swapped the two sets of changes. I recovered mine by path and **re-applied that agent's
edits by hand** to the five files we both touched, so nothing of theirs should be lost:

- `backend/tests/test_admin.py` — `{"maud", "edgar", "folio"}` (cuad dropped from the assertion)
- `docs/results/calibration.md` — "non-merger commercial contracts" (CUAD parenthetical dropped)
- `frontend/src/styles/shell.css` — `.arch__dormant rect` rule deleted
- `frontend/src/views/Admin.test.tsx` — the `CUAD is not overstated (#35)` describe block deleted
- `frontend/src/views/Overview.test.tsx` — `clauses` dropped from the count mocks

Worth a second pair of eyes: if that agent made further edits to those five files in the ~10 minutes
the stash race spanned, they are the ones at risk, and nowhere else.
