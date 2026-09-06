/**
 * This corpus's terms of art, moved from the platform's Term component (semantic-explorer-base#7).
 *
 * A shared glossary would be either wrong for every other domain or so generic it defines
 * nothing — "MAUD" and "fiduciary out" mean something to one reader and nothing to the next.
 */
import type { Glossary } from '@semantic-explorer-base/ui'

export const GLOSSARY: Glossary = {
  MAUD: {
    short: 'Merger Agreement Understanding Dataset',
    long: '152 public-target merger agreements from SEC filings, annotated by lawyers against the 92 ABA deal points. CC BY 4.0.',
  },
  'deal point': {
    short: 'A negotiated provision, as a fixed-vocabulary question',
    long: 'A provision written as a question with a fixed answer set — "is there a fiduciary out?". 92 of them, one per row per agreement.',
  },
  'fiduciary out': {
    short: 'The board may accept a better offer',
    long: 'A clause letting the target’s board back out of the deal for a superior proposal, subject to notice and matching rights.',
  },
  'SIC crosswalk': {
    short: 'Coarse self-reported industry code, mapped to a category',
    long: 'A crosswalk from EDGAR’s SIC codes to a coarser industry grouping. Inferred, never an expert label.',
  },
  EDGAR: {
    short: "The SEC's public filing system",
    long: 'Source of deal value, dates, parties, and the SIC code for each matter.',
  },
  'public target': {
    short: 'The company being acquired, listed publicly',
    long: 'MAUD covers only public-target deals — the target filed with the SEC, which is why EDGAR has a record for it.',
  },
  'reverse termination fee': {
    short: "The fee the BUYER pays if the deal breaks",
    long: 'Paid by the acquirer to the target on certain failures to close — the mirror of a target-side breakup fee.',
  },
  'k-anonymity': {
    short: 'No answer traceable to fewer than min_n records',
    long: 'The reason a thin slice is refused rather than answered: filtering to n=1 would recover one client\'s negotiated term through the analytics layer.',
  },
  min_n: {
    short: 'The k-anonymity / sample-size floor',
    long: 'Below this count a slice is refused rather than characterized — statistical honesty and a confidentiality control in one gate.',
  },
  inferred: {
    short: 'Derived by a classifier, not an expert label',
    long: 'Flagged wherever it appears so it is never mistaken for a lawyer’s annotation.',
  },
}
