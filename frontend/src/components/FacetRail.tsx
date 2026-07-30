import type { FacetsResponse } from '../types'

/**
 * The facet rail (#19).
 *
 * Two rules that are easy to get wrong and expensive to get wrong:
 *
 * 1. **A zero-count value renders disabled, never hidden.** What the corpus does not contain
 *    is information — hiding it makes an absent slice indistinguishable from one that was
 *    never offered.
 * 2. **Every count carries its denominator.** `n=25`, not a bare 25 floating beside a label.
 */
export function FacetRail({
  facets,
  loading,
  onToggle,
}: {
  facets: FacetsResponse | null
  loading: boolean
  onToggle: (group: string, value: string, code: string | null) => void
}) {
  return (
    <aside className="facets" aria-label="filters">
      {facets && (
        <p className="facets__total">
          <span className="facets__totalnum">{facets.total_n}</span> of {facets.unfiltered_n}{' '}
          matters
        </p>
      )}

      {loading && !facets && (
        <div className="facets__skeleton" aria-hidden="true">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="skeleton skeleton--facet" />
          ))}
        </div>
      )}

      {facets?.groups.map((group) => (
        <section
          key={group.key}
          className={`facet${group.unavailable ? ' facet--unavailable' : ''}`}
          data-testid={`facet-${group.key}`}
        >
          <h3 className="facet__title">
            {group.label} <span className="facet__n">n={group.total_n}</span>
          </h3>
          {group.unavailable && <p className="facet__unavailable">{group.unavailable}</p>}
          <ul className="facet__values">
            {group.values.map((value) => (
              <li key={value.value}>
                <button
                  type="button"
                  className={`facet__value${value.selected ? ' is-selected' : ''}`}
                  disabled={value.n === 0 || group.unavailable != null}
                  aria-pressed={value.selected}
                  aria-disabled={value.n === 0 || group.unavailable != null}
                  onClick={() => onToggle(group.key, value.value, value.code ?? null)}
                >
                  <span className="facet__label">{value.value}</span>
                  <span className="facet__count">n={value.n}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  )
}
