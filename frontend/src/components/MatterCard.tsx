import type { Matter } from '../types'

/**
 * One comparable deal (#19; the full card with drill-through is #20).
 *
 * Industry always renders with its inferred flag. It comes from a crosswalk over a coarse
 * self-assigned SIC code and is right about 85% of the time on a hand check — presenting it
 * beside MAUD's expert labels without a marker is the quiet error CLAUDE.md warns about.
 */
export function MatterCard({
  matter,
  focused,
  expanded,
  onFocus,
  onToggle,
}: {
  matter: Matter
  focused: boolean
  expanded: boolean
  onFocus: () => void
  onToggle: () => void
}) {
  return (
    <li
      className={`card${focused ? ' is-focused' : ''}`}
      data-testid={`matter-${matter.matter_id}`}
      aria-current={focused ? 'true' : undefined}
    >
      <button type="button" className="card__hit" onClick={onToggle} onFocus={onFocus}>
        <span className="card__title">
          {matter.target_name ?? matter.matter_id}
          {matter.acquirer_name && <span className="card__acquirer"> ← {matter.acquirer_name}</span>}
        </span>

        <span className="card__meta">
          {matter.industry && (
            <span className="tag">
              {matter.industry}
              {matter.is_inferred_industry && (
                <span className="tag__inferred" title="derived from SIC via a crosswalk, not an expert label">
                  inferred
                </span>
              )}
            </span>
          )}
          {matter.signing_date && <span className="card__date">{matter.signing_date}</span>}
          {matter.score !== null && (
            <span className="card__score" title="hybrid score within the filtered set">
              {matter.score.toFixed(3)}
            </span>
          )}
        </span>
      </button>

      {expanded && (
        <div className="card__detail">
          <dl className="card__dl">
            <dt>matter</dt>
            <dd>{matter.matter_id}</dd>
            {matter.score !== null && (
              <>
                <dt>vector</dt>
                <dd>{matter.vector_score?.toFixed(3)}</dd>
                <dt>bm25</dt>
                <dd>{matter.bm25_score?.toFixed(3)}</dd>
              </>
            )}
          </dl>
          <p className="card__note">Deal points and clause drill-through land in #20.</p>
        </div>
      )}
    </li>
  )
}
