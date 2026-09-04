import { Fragment, useEffect, useState } from 'react'
import type { TableRowsResponse, TableSchema } from '../types'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { TablesDiagram } from '../components/diagrams'
import { TablesExplainer } from '../components/explainers'

const TABLE_NAMES = ['matters', 'deal_points', 'folio_concepts', 'labels', 'ingest_runs']

/**
 * Tables — browsable raw data so nobody opens psql (#31). Explicitly requested.
 *
 * Sort, filter, and pagination all happen server-side (`/tables/*`) — this view never asks for
 * more than a page, and the server itself refuses a limit above its ceiling rather than
 * silently capping it. State (table, sort, filter, page) is mirrored into the URL query string
 * so a view is shareable without a backend change.
 */
export function Tables() {
  const initial = new URLSearchParams(window.location.search)
  const [table, setTable] = useState(initial.get('table') || 'matters')
  const [sort, setSort] = useState(initial.get('sort') || '')
  const [dir, setDir] = useState<'asc' | 'desc'>((initial.get('dir') as 'asc' | 'desc') || 'asc')
  const [filterColumn, setFilterColumn] = useState(initial.get('filter_column') || '')
  const [filterValue, setFilterValue] = useState(initial.get('filter_value') || '')
  const [offset, setOffset] = useState(Number(initial.get('offset') || 0))
  const [expanded, setExpanded] = useState<string | null>(null)
  const [expandedRow, setExpandedRow] = useState<Record<string, unknown> | null>(null)

  const [schema, setSchema] = useState<TableSchema | null>(null)
  const [data, setData] = useState<TableRowsResponse | null>(null)
  const limit = 25

  useEffect(() => {
    const params = new URLSearchParams({ table, sort, dir, offset: String(offset) })
    if (filterColumn) params.set('filter_column', filterColumn)
    if (filterValue) params.set('filter_value', filterValue)
    window.history.replaceState(null, '', `?${params}`)
  }, [table, sort, dir, filterColumn, filterValue, offset])

  useEffect(() => {
    // #38: a response landing after the table changed would overwrite the new schema with the
    // old one — the same guard Coverage and Explore already use
    let cancelled = false
    fetch(`/api/tables/${table}/schema`)
      .then((r) => r.json())
      .then((d) => !cancelled && setSchema(d))
    return () => {
      cancelled = true
    }
  }, [table])

  useEffect(() => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (sort) params.set('sort', sort)
    if (dir) params.set('dir', dir)
    if (filterColumn && filterValue) {
      params.set('filter_column', filterColumn)
      params.set('filter_value', filterValue)
    }
    let cancelled = false
    fetch(`/api/tables/${table}/rows?${params}`)
      .then((r) => r.json())
      .then((d) => !cancelled && setData(d))
    return () => {
      cancelled = true
    }
  }, [table, sort, dir, filterColumn, filterValue, offset])

  function toggleExpand(rowId: string) {
    if (expanded === rowId) {
      setExpanded(null)
      setExpandedRow(null)
      return
    }
    setExpanded(rowId)
    fetch(`/api/tables/${table}/rows/${encodeURIComponent(rowId)}`)
      .then((r) => r.json())
      .then(setExpandedRow)
  }

  function exportCsv() {
    const params = new URLSearchParams()
    if (sort) params.set('sort', sort)
    if (dir) params.set('dir', dir)
    if (filterColumn && filterValue) {
      params.set('filter_column', filterColumn)
      params.set('filter_value', filterValue)
    }
    window.location.href = `/api/tables/${table}/export.csv?${params}`
  }

  return (
    <div className="tables">
      <ExplainerPanel id="tables" title="What this tab is for: checking the numbers" diagram={<TablesDiagram />}>
        <TablesExplainer />
      </ExplainerPanel>
      <div className="tables__bar">
        <select
          aria-label="table"
          value={table}
          onChange={(e) => {
            setTable(e.target.value)
            setOffset(0)
            setSort('')
            setFilterColumn('')
            setFilterValue('')
          }}
        >
          {TABLE_NAMES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        {schema && (
          <>
            <select
              aria-label="filter column"
              value={filterColumn}
              onChange={(e) => {
                setFilterColumn(e.target.value)
                setOffset(0)
              }}
            >
              <option value="">filter column…</option>
              {schema.columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
            <input
              type="search"
              aria-label="filter value"
              placeholder="contains…"
              value={filterValue}
              onChange={(e) => {
                setFilterValue(e.target.value)
                setOffset(0)
              }}
            />
          </>
        )}

        <button type="button" className="tables__export" onClick={exportCsv}>
          export CSV
        </button>

        {schema && <span className="tables__count mono">n={schema.row_count}</span>}
      </div>

      {(!schema || !data) && <div className="skeleton skeleton--row" aria-label="loading table" />}

      {schema && data && (
        <>
          <div className="cov__scroll">
            <table className="tables__table">
              <thead>
                <tr>
                  {schema.columns.map((c) => (
                    <th key={c.name}>
                      <button
                        type="button"
                        className="tables__sort"
                        onClick={() => {
                          setDir(sort === c.name && dir === 'asc' ? 'desc' : 'asc')
                          setSort(c.name)
                        }}
                      >
                        {c.name}
                        {sort === c.name && (dir === 'asc' ? ' ▲' : ' ▼')}
                      </button>
                      <div className="tables__coltype">
                        {c.type} · null={c.null_count}
                        {c.is_inferred_flag && <span className="tables__inferredcol"> · inferred</span>}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => {
                  const rowId = String(row.id)
                  return (
                    <Fragment key={rowId}>
                      <tr
                        className="tables__row"
                        onClick={() => toggleExpand(rowId)}
                        data-testid={`row-${rowId}`}
                      >
                        {schema.columns.map((c) => (
                          <td key={c.name} className={c.is_inferred_flag ? 'tables__inferredcell' : ''}>
                            {formatCell(row[c.name])}
                          </td>
                        ))}
                      </tr>
                      {expanded === rowId && (
                        <tr className="tables__expanded">
                          <td colSpan={schema.columns.length}>
                            {expandedRow ? (
                              <dl className="tables__full">
                                {Object.entries(expandedRow).map(([k, v]) => (
                                  <div key={k}>
                                    <dt>{k}</dt>
                                    <dd>{formatCell(v)}</dd>
                                  </div>
                                ))}
                              </dl>
                            ) : (
                              <span className="admin__missing">loading…</span>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="admin__pager">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
              prev
            </button>
            <span className="mono">
              {offset + 1}–{Math.min(offset + limit, data.total_count)} of {data.total_count}
            </span>
            <button
              type="button"
              disabled={offset + limit >= data.total_count}
              onClick={() => setOffset(offset + limit)}
            >
              next
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string' && value.length > 80) return value.slice(0, 80) + '…'
  return String(value)
}
