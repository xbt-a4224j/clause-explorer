import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

/**
 * The per-tab explainer (#33, #34, #35).
 *
 * Every tab answers a different question and none of them announce which. This is the
 * standing frame: what this tab is for, what you can do here, and why the answer is worth
 * more than the obvious alternative.
 *
 * Expanded by default — the first visit is the one that needs it — except where a tab's
 * primary surface is the data itself (Deal Terms), which starts collapsed so the empty-state
 * CTA or the table is the first thing on screen. The choice is persisted
 * per panel so a reviewer who has internalised a tab is not re-taught it on every load,
 * which matters most on Label, where the loop targets under five seconds per item.
 *
 * `<button aria-expanded>` rather than `<details>`: the tabs bind bare letter keys
 * (y/n/e/s, j/k, /) at the window, and a focused `<summary>` swallows Enter and Space in
 * ways that differ across browsers. An explicit button keeps the keyboard contract legible.
 */

const PREFIX = 'clause-explorer.explainer.'

function readStored(id: string, defaultOpen: boolean): boolean {
  try {
    const stored = window.localStorage.getItem(PREFIX + id)
    if (stored === null) return defaultOpen
    return stored !== 'collapsed'
  } catch {
    // Safari private mode throws on localStorage access. An explainer that cannot remember
    // a preference is a small loss; one that crashes the tab is not.
    return defaultOpen
  }
}

export function ExplainerPanel({
  id,
  title,
  children,
  diagram,
  defaultOpen = true,
}: {
  /** stable key for the persisted choice; must not change between releases */
  id: string
  /** the control's accessible name — phrase it as the question the tab answers */
  title: string
  children: ReactNode
  diagram?: ReactNode
  /** first-visit state; dense tabs whose primary surface is the data start collapsed */
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(() => readStored(id, defaultOpen))

  useEffect(() => {
    try {
      window.localStorage.setItem(PREFIX + id, open ? 'expanded' : 'collapsed')
    } catch {
      /* see readStored */
    }
  }, [id, open])

  const toggle = useCallback(() => setOpen((o) => !o), [])

  return (
    <section className={`explain${open ? '' : ' is-collapsed'}`} aria-labelledby={`${id}-title`}>
      <button
        type="button"
        className="explain__toggle"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={toggle}
        id={`${id}-title`}
      >
        <span className="explain__chevron" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        {title}
      </button>
      <div className="explain__body" id={`${id}-body`} hidden={!open}>
        {diagram && <div className="explain__diagram">{diagram}</div>}
        <div className="explain__prose">{children}</div>
      </div>
    </section>
  )
}
