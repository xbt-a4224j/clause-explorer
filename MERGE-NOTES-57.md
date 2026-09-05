# Merge notes — #57 and the UX pass

`README.md` was not edited, per the brief. This is every passage in it that these commits make
wrong, plus the ones that were already wrong before them and are worth fixing in the same pass.

## What these commits made wrong

### 1 · The Ask/Semantic Layer screenshot and its caption

`README.md:45` embeds `docs/img/refusal.png` and `README.md:47` captions it *"Semantic
Layer…"*. Three things changed underneath it:

- The tab has been called **Ask** since #48; the caption still says Semantic Layer. (Already
  wrong before this round — noted here because the screenshot is being regenerated anyway.)
- The builder's chips now read the catalog **title** over the qualified name — `Deal Points N`
  over `deal_points.n` — instead of the bare suffix over the cube name. The image is stale.
- The builder no longer offers `matters.*` or `industries.*`. The old image shows 35 group-by
  chips; the current build shows 18.

The caption's substance still holds: no free-text box in the builder, the server refuses at
`n=1`, and a raw `curl` gets the same answer. All three verified against the running stack.

### 2 · Every other committed screenshot

`docs/img/{overview,explore,deal-terms,deal-terms-drill,label}.png` all predate this round.
The Overview and Label diagrams changed (four sub-captions shortened so they sit inside the
node they label), the Ask tab reordered, and the Label progress line was rewritten.

Regenerate with the app up:

    cd frontend && node scripts/shots.mjs

`scripts/shots.mjs` was fixed in this round for two things that would otherwise have made that
run produce a wrong set silently: the `semantic-layer` shot now opens the vocabulary
disclosure before pointing a callout at `.cat__list`, and the `refusal` shot scopes `.qb__run`
to the builder — Ask's Interpret button carries the same class and now sits above it, so an
unscoped locator waits forever on a disabled button.

### 3 · The tab table

`README.md:95` describes **Semantic Layer** as *"The vocabulary the agent may select from,
read live from Cube, with a query builder that has no free-text box…"*. Still true, and now
more so: the vocabulary is what the agent may select from rather than every cube in `/meta`,
and the Ask box's filter values are a `<select>` over the corpus's own values, so there is no
free-text path on that row either. The row should say **Ask**, not Semantic Layer.

### 4 · Nothing in the README quotes the label space

Worth knowing anyway, because the number moved and it is the sort of figure that gets quoted:
`/agent/catalog` reported `label_space: 48` and now reports **29** (11 measures, 18
dimensions). The old figure counted `matters` and `industries`, which the agent cannot select
from — so the claim rendered beside it, "the model chooses from these names and no others",
was false by 19. Measured:

    curl -s localhost:8000/agent/catalog | python3 -c "import json,sys; b=json.load(sys.stdin); print(len(b['measures']), len(b['dimensions']), b['label_space'])"
    11 18 29

## Passages that were already wrong before this round

Listed because a reader hitting them will assume this round broke them.

- **`README.md:10`** — *"after Coverage: four tabs are the product, four are the evidence"*.
  There are six tabs, split three and three. #48 cut Coverage and Tables.
- **`README.md:52–56`** — the Coverage screenshot and caption. **The Coverage tab does not
  exist**; #48 removed it. `docs/img/coverage.png` is an image of a deleted view, and
  `scripts/shots.mjs` no longer generates it.
- **`README.md:88`** — the **Coverage** row of the tab table. Same.
- **`README.md:96`** — the **Tables / Admin** row. Both are gone: Tables was cut in #48, and
  #54 folded Admin's evidence into **Trust** and its operator surface into a collapsed section
  at the bottom of that tab.
- **`README.md:58`** — *"Admin publishes accuracy per deal point on held-out gold"*. That is
  Trust now. (The same stale reference appeared twice in the Label tab's own copy and was
  fixed in this round.)
- **`docs/img/coverage.png`** — should be deleted along with its README block.

## Things this round changed that are not in the README but change behaviour

- **`POST /agent/members`** is new. It answers, per selected name: catalog title and
  description, the closed vocabulary behind a dimension, corpus coverage as `populated of
  total`, and a sentence when no selection over that member can produce an answer. It is a
  separate route from `/agent/ask` because `ask.py` must never touch Cube's `/load` and a test
  asserts that on every path.
- **`GET /label/queue`** items now carry `allowed_positions`.
- **`GET /agent/catalog`** is restricted to `SELECTABLE` minus `EXCLUDED_MEASURES`. Any
  client relying on it to enumerate `matters.*` will now see nothing there. Nothing in this
  repo did.
- **The header search box does something.** It rendered on five of six tabs with no handler at
  all; `?` advertised "/ focus search". Enter now carries what you typed to Explore, via the
  existing journey-seed mechanism, and the shortcut help says so.

## Not done, and why

- **The committed screenshots were not regenerated.** The brief scoped this round to code and
  the README is off limits; regenerating `docs/img/*.png` would put stale captions next to
  fresh images and churn six binaries in a diff nobody asked for. The command is above.
- **`cube/model/*.yml` titles were not touched.** Chip titles come from Cube's auto-derived
  ones — `Deal Points N`, `Comparable Deals Deal Size Band` — which are legible but wordy. Real
  `title:` entries in the YAML would read better; the brief forbids restarting Cube, and the
  running container bind-mounts the main checkout's `cube/model`, not this worktree's, so the
  change could not have been verified here.
- **`updated_at` dimensions are still agent-selectable** on both cubes, despite their own
  descriptions saying "Operational, not analytical". Excluding them is a `select.py` decision
  with an eval label-space consequence, which is its own issue rather than a UX fix.
