import type { AgentSelection } from '../types'

/**
 * The resolved query, shown above every agent answer (#26).
 *
 * Enum-constraining the selection (#24) does not make a wrong interpretation impossible — it
 * relocates the risk: a valid-but-wrong selection still returns a real number for the wrong
 * question. This line is the one thing that lets a domain expert catch that before it reaches
 * a pitch deck, so every component of the selection renders here, in plain language, including
 * which filter values were *resolved* rather than typed verbatim (#25) and whether any inferred
 * dimension was touched.
 */
export function ResolvedQuery({
  selection,
  onEdit,
}: {
  selection: AgentSelection
  onEdit: (selection: AgentSelection) => void
}) {
  const measure = selection.measures.map(shortName).join(', ') || '—'
  const dims = selection.dimensions.map(shortName)
  const range = selection.timeDimensions.map((t) => t.range).join(' · ')

  return (
    <p className="resolved" data-testid="resolved-query">
      <span className="resolved__measure">{measure}</span>
      {dims.length > 0 && <span> · {dims.join(', ')}</span>}
      {selection.filters.map((f) => (
        <span key={f.member} className="resolved__filter" data-testid={`resolved-filter-${f.member}`}>
          {' · '}
          {f.resolved && f.raw ? (
            <>
              <span className="resolved__raw">{f.raw}</span> <span aria-hidden="true">→</span>{' '}
              <span className="resolved__value">{f.values.join(', ')}</span>
            </>
          ) : (
            <span className="resolved__value">{f.values.join(', ')}</span>
          )}
        </span>
      ))}
      {range && <span> · {range}</span>}
      <span className="mono"> · n={selection.n}</span>
      {selection.is_inferred && (
        <span className="resolved__inferred" title="this query touches at least one inferred dimension">
          {' '}
          · inferred
        </span>
      )}
      <button type="button" className="resolved__edit" onClick={() => onEdit(selection)}>
        edit this query
      </button>
    </p>
  )
}

function shortName(field: string): string {
  return field.includes('.') ? field.split('.').slice(1).join('.') : field
}
