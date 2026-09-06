# Colour by mechanism

Portable design guidance. Nothing here is specific to merger agreements — it applies to any app
whose central claim is *this number came from here and that one came from there*.

## The problem it solves

A disciplined neutral design system — Primer, or any well-behaved greyscale-plus-one-accent set —
makes an app look like an instrument. That is the right choice for a reading surface, and it has a
cost nobody mentions: **the neutrality that makes it look serious also makes the architecture
invisible.**

If everything on screen is the same grey, a reader cannot tell that the counts came from a governed
semantic layer while the ranking came from hybrid retrieval. They have to take your word for it. A
sceptical reviewer — the one asking *"where is the model actually used, versus a plain database
query?"* — is asking a question the UI should already have answered.

That is partly a **visual** problem, and colour is the cheapest instrument for it.

## The rule

**Colour encodes which mechanism produced what you are looking at. Nothing else.**

Not status. Not component type. Not emphasis. One hue per mechanism, applied consistently
everywhere that mechanism's output appears, and applied nowhere else.

## Six constraints

**1 · One hue per mechanism, two to four mechanisms.** More than four and the reader is learning a
legend instead of reading the app. If you have five, you have not finished deciding what your
product does.

**2 · A combination is rendered as a blend of its parts, never a new hue.** Hybrid retrieval is a
weighted mix of keyword and vector scoring, so the hybrid control gets a gradient between the
keyword hue and the vector hue. The picture then matches the arithmetic, and the reader infers the
relationship without a caption. Giving hybrid its own third colour would imply a third independent
signal, which is a lie about the design.

**3 · Colour rides on hairlines, underlines and labels — never fills, never the number itself.**
A 2px underline on the active control; a 2px left border on the panel; the word `bm25` in its
mechanism's colour. A coloured *number* reads as a status ("is 89 bad?"), and a coloured *fill*
turns a reading surface into a dashboard. The body of the app stays exactly as neutral as it was.

**4 · Never colour alone — always pair the hue with its word.** `Keyword`, `vector`, `bm25`. This is
not politeness; it is the only thing that works in print, in greyscale, and for a reader with
colour-vision deficiency. It is also what makes a low CVD separation score acceptable when you
cannot avoid one.

**5 · Validate the palette with your accent already in the set.** This is the constraint people miss.
Your existing accent colour owns a region of colour space and nothing else may live there. Run a
real checker; do not eyeball ΔE.

**6 · Status colours are a separate, declared vocabulary.** Warn and danger are not mechanisms. Give
them their own tokens, and make sure they are actually *in* your token file — see the audit below.

## The procedure

```
1. List your mechanisms.            two to four. name them as verbs the user would recognise
2. Draft hues from your EXISTING    primitives only — never invent a hex. staying inside the
   design system's primitives       design language is most of why this reads as deliberate
3. Validate WITH the accent in it   node validate_palette.js "<hues>,<accent>" --mode light
4. Iterate until every check passes lightness · chroma · CVD separation · normal-vision · contrast
5. Declare as tokens, and record    the rejected candidates and WHY are the useful half of
   the failures in the comment      the comment; without them the next person retries them
6. Teach the colours where the      the control that NAMES the mechanisms is the natural
   mechanisms are named             legend. Do not build a separate key nobody reads
```

### What step 3 actually catches

Two candidates were rejected here before one passed, and both failures were invisible by eye:

| candidate for "meaning" | result |
|---|---|
| teal `#0f7490` | **FAIL** — ΔE 12.7 against the accent (floor is 15) |
| indigo `#6639ba` | **FAIL** — ΔE 13.6 against the accent |
| pink `#bf3989` | PASS — all five checks |

The lesson generalises: **an accent blue owns the entire blue–purple–teal region.** Whatever your
accent is, the neighbouring third of the wheel is spoken for, and the mechanism hues have to go
somewhere else. That is not obvious until a checker tells you.

## Worked example

Three mechanisms, three Primer primitives, every one ≥ 5:1 on white:

```css
--mech-governed: #8250df;   /* purple.fg — the semantic layer computed this  */
--mech-exact:    #bc4c00;   /* orange.fg — keyword/BM25: the literal words   */
--mech-meaning:  #bf3989;   /* pink.fg   — embeddings: things that read alike */
```

```
$ node validate_palette.js "#8250df,#bc4c00,#bf3989,#0969da" --mode light
  [PASS] Lightness band       [PASS] Chroma floor        [PASS] CVD separation
  [PASS] Normal-vision floor  [PASS] Contrast vs surface
  -> ALL CHECKS PASS
```

Applied in three places and no others:

```css
/* the control that names the mechanisms — this is the legend */
.rank__btn--exact.rank__btn--on   { color: var(--mech-exact);   border-bottom-color: var(--mech-exact); }
.rank__btn--meaning.rank__btn--on { color: var(--mech-meaning); border-bottom-color: var(--mech-meaning); }
.rank__btn--hybrid.rank__btn--on  {
  color: var(--ink);   /* the blend gets no hue of its own */
  border-image: linear-gradient(90deg, var(--mech-exact), var(--mech-meaning)) 1;
}

/* the per-result scores, each in the colour of the half that produced it */
.card__scores dt:nth-of-type(2) { color: var(--mech-meaning); }
.card__scores dt:nth-of-type(3) { color: var(--mech-exact); }

/* anything the governed layer computed: a hairline, never a fill */
.qb__json, .terms__caption { border-left: 2px solid var(--mech-governed); padding-left: 8px; }
```

## Run the token audit while you are in there

Adding mechanism tokens is the natural moment to check whether your declared design system is the
one actually in the stylesheet. Ours was not:

```
$ grep -roh "#[0-9a-fA-F]\{6\}" src/styles/shell.css src/components/*.tsx | sort -u | wc -l
19
```

against a `CLAUDE.md` that said the only hardcoded hex was two status dots. Of those 19, eight were
a declared and separately validated chart-series palette — fine, just living in the wrong file. The
other **eleven were an undeclared amber/red status vocabulary** that had grown organically: the same
amber pair retyped four times, plus a near-miss duplicate (`#6a4a00`/`#fffaf0`/`#e6d8b5`) sitting
four lines from the amber it meant to reuse.

That is how it always goes. Nobody adds a palette; somebody needs a warning box at 1am and types a
hex, and six months later there are four ambers that are almost the same colour.

```css
--warn: #9a6700;  --warn-ink: #6a4500;  --warn-bg: #fff8e5;  --warn-border: #e6d3a3;
--danger: #d1242f;  --danger-ink: #8a1a22;  --danger-bg: #fff5f5;
```

Twenty literal occurrences collapsed into seven tokens.

## The test that keeps it honest

A rule nobody can check is a rule that decays. This one is greppable, so pin it:

```
no hardcoded hex outside the token file, except inside a block that documents its own validation
```

Same shape as the existing test that greps the frontend to make sure no band threshold is
hardcoded outside the Cube model. The point of both is that the *documentation* of a design system
is worth nothing next to a gate that fails.
