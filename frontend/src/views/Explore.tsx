import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FacetRail } from '../components/FacetRail'
import { MatterCard } from '../components/MatterCard'
import { ResultsSkeleton } from '../components/Skeleton'
import type { ComparablesResponse, FacetsResponse, Matter } from '../types'

/**
 * Explore — faceted comparable-deal search (#19).
 *
 * Three states are designed rather than defaulted: loading is a skeleton shaped like the
 * result list (not a spinner), empty says which filters produced nothing and offers to clear
 * them, and a failed semantic layer says so explicitly instead of rendering zero counts.
 * "No results" and "the count service is down" must never look the same.
 *
 * Every count carries its denominator. Facet values with n=0 render disabled rather than
 * disappearing — what the corpus does *not* have is information.
 */

interface Props {
  // MutableRefObject, not RefObject: the shell creates it with useRef<HTMLInputElement>(null),
  // so its current is nullable and React 18's ref prop type requires the mutable form.
  searchRef: React.MutableRefObject<HTMLInputElement | null>
}

export interface Filters {
  folio_industry_label: string | null
  /** The FOLIO code behind the selected label. This, not the label, is what /comparables gets. */
  folio_industry_code: string | null
  signing_year: string | null
  deal_size_band: string | null
}

const EMPTY: Filters = {
  folio_industry_label: null,
  folio_industry_code: null,
  signing_year: null,
  deal_size_band: null,
}

export function Explore({ searchRef }: Props) {
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [description, setDescription] = useState('')
  const [facets, setFacets] = useState<FacetsResponse | null>(null)
  const [results, setResults] = useState<ComparablesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [cursor, setCursor] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const activeCount = Object.values(filters).filter(Boolean).length

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const facetBody = {
      folio_industry_label: filters.folio_industry_label,
      signing_year: filters.signing_year ? Number(filters.signing_year) : null,
      deal_size_band: filters.deal_size_band,
    }
    const comparablesBody = {
      description: description.trim() || null,
      // the industry filter belongs on the server: #18 filters in Postgres and builds the
      // hybrid index over exactly the survivors, so scores are relative to the requested
      // slice. Filtering the response here instead would rank against the whole corpus and
      // report a candidate_count for matters the partner never asked about.
      folio_industry_code: filters.folio_industry_code,
      signed_from: filters.signing_year ? `${filters.signing_year}-01-01` : null,
      signed_to: filters.signing_year ? `${filters.signing_year}-12-31` : null,
      deal_size_band: filters.deal_size_band,
      limit: 25,
    }

    Promise.all([
      post<FacetsResponse>('/api/facets', facetBody),
      post<ComparablesResponse>('/api/comparables', comparablesBody),
    ])
      .then(([f, r]) => {
        if (cancelled) return
        setFacets(f)
        setResults(r)
        setCursor(0)
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))

    return () => {
      cancelled = true
    }
  }, [filters, description])

  // No client-side filtering: the server is the authority on what is in the slice, and dropping
  // rows here would put the visible list and `candidate_count` into disagreement.
  const matters: Matter[] = useMemo(() => results?.matters ?? [], [results])

  const move = useCallback(
    (delta: number) => {
      setCursor((c) => Math.max(0, Math.min(matters.length - 1, c + delta)))
    },
    [matters.length],
  )

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null
      const typing =
        el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
      if (typing && e.key !== 'Escape') return

      if (e.key === 'j') {
        e.preventDefault()
        move(1)
      } else if (e.key === 'k') {
        e.preventDefault()
        move(-1)
      } else if (e.key === 'Enter' && matters[cursor]) {
        e.preventDefault()
        setExpanded((id) => (id === matters[cursor].matter_id ? null : matters[cursor].matter_id))
      } else if (e.key === 'f') {
        e.preventDefault()
        listRef.current?.ownerDocument
          .querySelector<HTMLButtonElement>('.facet__value')
          ?.focus()
      } else if (e.key === 'Escape') {
        setFilters(EMPTY)
        setDescription('')
        setExpanded(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [move, matters, cursor])

  function toggle(group: string, value: string, code: string | null) {
    setFilters((f) => {
      if (group === 'industry') {
        const clearing = f.folio_industry_label === value
        return {
          ...f,
          folio_industry_label: clearing ? null : value,
          folio_industry_code: clearing ? null : code,
        }
      }
      const key = group === 'year' ? 'signing_year' : 'deal_size_band'
      return { ...f, [key]: f[key] === value ? null : value }
    })
  }

  return (
    <div className="explore">
      <div className="explore__search">
        <input
          ref={searchRef}
          className="explore__input"
          type="search"
          placeholder="Describe the deal in front of you…  ( / to focus )"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          aria-label="describe the deal"
        />
        {results && (
          <p className="explore__resolved" data-testid="resolved-query">
            {describeQuery(results, filters)}
          </p>
        )}
      </div>

      <div className="explore__body">
        <FacetRail
          facets={facets}
          loading={loading}
          onToggle={toggle}
        />

        <section className="explore__results" aria-label="results">
          {error && (
            <div className="state state--error" role="alert">
              <h3 className="state__title">Counts unavailable</h3>
              <p className="state__body">{error}</p>
              <p className="state__hint">
                This is not “no results” — the semantic layer did not answer, so no number here
                would be trustworthy.
              </p>
            </div>
          )}

          {!error && loading && <ResultsSkeleton />}

          {!error && !loading && matters.length === 0 && (
            <div className="state state--empty">
              <h3 className="state__title">No comparable deals in this slice</h3>
              <p className="state__body">
                {activeCount === 0
                  ? 'The corpus is loaded but returned nothing for this description.'
                  : `${activeCount} filter${activeCount > 1 ? 's' : ''} applied. The corpus has no matters that satisfy all of them.`}
              </p>
              <button type="button" className="state__action" onClick={() => setFilters(EMPTY)}>
                Clear filters
              </button>
            </div>
          )}

          {!error && !loading && matters.length > 0 && (
            <>
              <p className="explore__count">
                showing {matters.length} of {results?.candidate_count ?? matters.length} matching ·{' '}
                <span className="muted">n={results?.candidate_count ?? matters.length}</span>
              </p>
              <ul className="explore__list" ref={listRef}>
                {matters.map((matter, i) => (
                  <MatterCard
                    key={matter.matter_id}
                    matter={matter}
                    focused={i === cursor}
                    expanded={expanded === matter.matter_id}
                    onFocus={() => setCursor(i)}
                    onToggle={() =>
                      setExpanded((id) => (id === matter.matter_id ? null : matter.matter_id))
                    }
                  />
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

/** The resolved query, shown above every answer so a domain expert can catch a misread (#26). */
function describeQuery(results: ComparablesResponse, filters: Filters): string {
  const parts: string[] = []
  const applied = results.applied_filters
  if (filters.folio_industry_label) parts.push(filters.folio_industry_label)
  if (applied.signed_from) parts.push(`signed ${applied.signed_from} to ${applied.signed_to}`)
  if (applied.deal_size_band) parts.push(applied.deal_size_band)
  parts.push(applied.ranked_by)
  return `${parts.join(' · ')} · n=${results.candidate_count}`
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? `request failed (${response.status})`)
  }
  return payload as T
}
