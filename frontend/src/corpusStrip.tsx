/**
 * This corpus's provenance line on Explore: which sources, what is inferred, what date range.
 *
 * A figure with no source is unverifiable (#35), and WHICH sources — and whether one of them is
 * inferred rather than labelled — is a claim about this specific corpus. The platform's Explore
 * view supplies the live counts; this is the prose that explains where they came from.
 */
import { Term, type CorpusCounts, type Glossary } from '@semantic-explorer-base/ui'

export function corpusStrip(glossary: Glossary) {
  return (counts: CorpusCounts) => (
    <p className="explore__corpus mono">
      {counts.records} matters · {counts.facts.toLocaleString()} deal points · {counts.categories} industries
      <span className="explore__prov">
        records and deal points from <Term glossary={glossary}>MAUD</Term> (expert-labelled) ·
        industries from the <Term glossary={glossary}>SIC crosswalk</Term> via{' '}
        <Term glossary={glossary}>EDGAR</Term> (<Term glossary={glossary}>inferred</Term>) ·
        2020-03-13 to 2021-11-21
      </span>
    </p>
  )
}
