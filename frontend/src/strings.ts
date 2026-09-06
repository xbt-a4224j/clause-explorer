/**
 * This corpus's words, in the shape the platform asks for.
 *
 * The measured claim behind `QuorumStrings`: a fork of this app for a health-claims corpus
 * diverged on the frontend almost entirely in strings. The tell that it had not really been
 * generalised was a tab still labelled "Deal Terms" in a claims application — a label nobody
 * remembered to change, under an id (`deal-terms`) that nobody thought to change either.
 *
 * The id is now `terms` and lives in the platform. The LABEL is still "Deal Terms", because
 * this is a legal product and should read like one. That is the split: shared components,
 * unshared words.
 */
import type { QuorumStrings } from '@semantic-explorer-base/ui'
import { GLOSSARY } from './glossary'

export const STRINGS: QuorumStrings = {
  appName: 'Clause Explorer',
  corpusDescription: '152 public-target merger agreements with 47k expert labels',

  record: 'matter',
  records: 'matters',

  subject: 'deal point',
  subjects: 'deal points',

  // Not `records`, deliberately. A partner says "deals"; the thing being counted is
  // "agreements". Collapsing the two puts the wrong noun in half the sentences on the page.
  colloquial: 'deals',

  glossary: GLOSSARY,

  // What a fact's source text is called here. A wrong word tells the reader they are looking
  // at something they are not — and MAUD's spans are often an envelope rather than a clause,
  // which the drill-through labels separately.
  sourceText: 'clause',

  // The Ask placeholder. Content rather than vocabulary: a bad example teaches the wrong thing
  // about what this corpus can answer.
  exampleQuestion: 'healthcare cash deals, what did boards get on fiduciary outs',

  heldOutClaim:
    "Every item queued here is one of the 20 held-out matters — documents MAUD already has a " +
    "lawyer's answer for.",

  noSpanReason:
    'No quotable clause: this deal point is answered from the agreement as a whole. Open the ' +
    'matter for the surrounding text.',

  tabs: {
    overview: { label: 'Overview', hint: 'what this is and how it works' },
    ask: { label: 'Ask', hint: 'a question becomes a governed number, or a refusal' },
    explore: { label: 'Explore', hint: 'find comparable deals' },
    terms: { label: 'Deal Terms', hint: 'what was negotiated across a set' },
    trust: { label: 'Trust', hint: 'where the model is trusted, and where it is not' },
    label: { label: 'Label', hint: 'review the uncertainty queue' },
  },
}
