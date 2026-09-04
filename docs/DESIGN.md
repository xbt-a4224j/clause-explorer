# Design

**`frontend/src/styles/tokens.css` is the authority.** Colour, type, radius and spacing are
defined there, once, as CSS custom properties. Read that file before changing anything visual;
this page only records the handful of rules that are not obvious from it.

This file used to be a 3,031-word vendored spec for Linear's dark marketing site — a four-step
surface ladder on `#010102`, a lavender accent, pricing tabs, testimonial cards, a CTA banner.
None of that shipped. The palette was superseded by GitHub Primer light (see CLAUDE.md, *Design
system*), and the component catalogue described a marketing page this repo does not have.
Keeping it invited a reader to treat it as the spec and the code as drift. #45 replaced it with
what is actually followed.

## What is actually followed

**Density.** 4px base unit. The spacing tokens are `--pad-sm` 8px, `--pad-md` 12px, `--pad-lg`
20px, and there is deliberately no larger one — a section gap wider than 20px makes a dense
instrument read as a marketing page. Table cells and list rows use `--pad-sm`; panel interiors
use `--pad-md`. Body text is 14px; meta lines, table cells and sample-size annotations are
10–12px. Contract prose in the drill-through is monospace at 12–13px, which is the size the
light palette exists to serve.

**Component shape.** One radius, `--radius` 6px, on every panel, card, input and button. No
pills, no second radius. Surfaces are separated by a 1px `--hairline` border on `--surface-1`
over a `--canvas` page, never by a shadow — there is no elevation scale and nothing in this app
lifts. Panels are `.sem__pane`-shaped: hairline border, 6px radius, white, `--pad-md` inside.

**Accent.** `--accent` appears on focus rings, the brand mark, and intentional CTAs. Never
decoratively, never as a fill for a whole surface.

**Diagrams** are inline SVG using the same tokens, so they cannot drift from the palette, and
they carry `role="img"` with a `<title>` and a `<desc>` restating the content in words. They are
capped at their authored width rather than stretched to the panel; an 11px label rendered at
22px reads as a poster, not a reference.

**States are designed, not defaulted.** Loading, empty, and *refusal* each have their own
visual treatment, and refusal is visually distinct from empty — "we will not answer this" and
"there is nothing here" are different statements.

## Where the rest of the rules live

- Colour tokens and their WCAG contrast ratios: `frontend/src/styles/tokens.css`
- The rules a reviewer is most likely to break (counts vs percentages, every number carries its
  denominator, drill-through is mandatory, keyboard-first): CLAUDE.md, *Design system*
- Everything else: `frontend/src/styles/shell.css`, which is organised by view
