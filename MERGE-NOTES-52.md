# Merge notes — #52 (Label: buttons instead of keyboard shortcuts, and show what the decisions changed)

Files this branch deliberately did **not** touch, because another agent owns them or the
instruction was explicit. Each item below is a change #52 makes necessary somewhere else.

## README.md — two places now describe behaviour that no longer exists

I was told not to edit `README.md`, so these are unapplied.

1. **The tab table, "the four behind the divider"** (line 97). The row reads:

   > **Label** | A review queue ranked by disagreement between two extractors. Decisions feed the
   > next calibration run. …

   As committed it does not actually say "keyboard-driven", so it survives #52 unchanged. The
   claim about keyboard driving lives in **`CLAUDE.md`** instead, in *The tabs* table:

   > | **Label** | KM | keyboard-driven labeling that feeds the review queue and re-calibration |

   That line is now false. Suggested replacement: `labeling that feeds the review queue and
   re-calibration`. (`CLAUDE.md` was left alone on the same reasoning as `README.md` — it is a
   shared file every agent on this round is reading.)

2. **The Label screenshot caption** (lines 62–67). The caption itself does not name keystrokes,
   but the screenshot it points at — `docs/img/label.png` — shows the old hint line
   `y accept · n reject & correct · e edit · s skip · ? help` and shows no buttons and no
   before/after panel. **The image needs recapturing** after this merges; the caption text can
   stand, though it would be worth adding that the before/after figures are now on the tab
   itself rather than only on Admin.

## journeys.ts — journey 3's card (do not apply from this branch; I was told not to touch it)

Journey 3 (`id: 'trust-the-extractor'`) currently has these steps:

```ts
steps: [
  'Admin · accuracy per deal point',
  'Label · disagreements first',
  'decide, by keyboard',
  'Admin · the number moves',
],
```

Step 3 names an interaction that no longer exists, and step 4 sends the reader to Admin for a
number that is now at the top of the Label tab. Suggested replacement:

```ts
steps: [
  'Admin · accuracy per deal point',
  'Label · disagreements first',
  'accept, correct, edit or skip',
  'Label · the panel says it went down',
],
```

The `outcome` line still holds as written. If you want the card to carry the direction, the
minimal edit is to end it `…with the reviewer's decisions graded into that number rather than
filed away — on the six recorded so far, downwards.`

## tabs.ts — nothing removed from `SHORTCUTS`, and that is not an oversight

The acceptance criterion says the shortcuts come out of "the Label tab, the help overlay and the
`SHORTCUTS` list". The list as committed is:

```ts
export const SHORTCUTS: ReadonlyArray<[string, string]> = [
  ['1 – 8', 'switch tab'],
  ['/', 'focus search'],
  ['j / k', 'move through results'],
  ['Enter', 'open the focused result'],
  ['?', 'show this help'],
  ['Esc', 'close / clear'],
]
```

`y`, `n`, `e` and `s` were never in it — they were advertised only by Label's own hint line and
its own `?` dialog, both of which this branch deletes. So `tabs.ts` is untouched. The remaining
six entries all belong to the shell or to Explore and are still live.

One consequence worth knowing: Label used to swallow `?` for its own dialog. It no longer binds
anything at the window, so `?` on the Label tab now opens the **shell's** shortcut overlay, which
is the correct behaviour and is what the `SHORTCUTS` list describes.

## Admin.tsx — what I changed, and the one thing I could not

Per the constraint I only touched the labels-calibration section. The duplicated headline
(`calibration-labels-summary`) and the duplicated corpus caveat (`calibration-labels-caveat`)
are gone; a pointer paragraph (`calibration-labels-pointer`) sends the reader to the Label tab,
and a short provenance line (`calibration-labels-provenance`) keeps the command beside the
per-deal-point table, which stays.

**It is a textual pointer, not a link.** `Admin` takes no props and the tab switcher lives in
`App.tsx` state; wiring a real click-through means adding a navigation prop in `App.tsx`, which is
outside what I was allowed to touch. If someone is already editing `App.tsx` this round, the
change is: pass `onOpenTab={setActive}` to `<Admin />` and turn the words "the **Label** tab" into
a `.qb__linkbtn`-styled button. Two Admin tests moved with the copy
(`frontend/src/views/Admin.test.tsx`, the `#41` describe block) — that file was not on my list
either, but the gate cannot be green without it.

## Stale copy elsewhere that #52 does not fix

- `frontend/src/components/ExplainerPanel.tsx`, the docstring: *"the tabs bind bare letter keys
  (y/n/e/s, j/k, /) at the window"*. After this branch only `j/k` and `/` are true. The reasoning
  in that comment — that `<button aria-expanded>` beats `<details>` because a focused `<summary>`
  swallows Enter and Space — still holds, and matters more now that the queue is driven entirely
  by buttons. Left alone because the file is shared by every tab; suggested edit is to drop
  `y/n/e/s` from the parenthesis.
- `docs/walkthrough.md`, the *Label* section (around line 373), still says **"nothing reads that
  table yet"** and that "a keystroke here does not currently move any number in the product".
  That was already stale before #52 — #41 closed the loop — and #52 makes the word "keystroke"
  wrong as well. Out of scope here; worth its own issue.
- `docs/img/label.png` — see README point 2 above.
