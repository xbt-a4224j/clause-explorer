/**
 * The eight tabs, in demo order. Overview is first and is the landing tab (#39): every
 * other view assumes you already know what the system is, and a visitor who starts on
 * Explore sees a faceted search without ever learning that retrieval is hybrid or that
 * aggregate figures come from a governed semantic layer rather than from generation.
 *
 * Explore remains the entry point for demo script 1 — a partner who knows the product
 * should still land one key away from it.
 *
 * Order is load-bearing: the number-key shortcut is the index, so reordering this array
 * silently rebinds every shortcut.
 */
export type TabId =
  | 'overview'
  | 'explore'
  | 'deal-terms'
  | 'coverage'
  | 'semantic-layer'
  | 'tables'
  | 'admin'
  | 'label'

export interface Tab {
  id: TabId
  label: string
  hint: string
  audience: 'partner' | 'km' | 'operator' | 'engineer'
}

export const TABS: readonly Tab[] = [
  {
    id: 'overview',
    label: 'Overview',
    hint: 'what this is and how it works',
    audience: 'partner',
  },
  {
    id: 'explore',
    label: 'Explore',
    hint: 'find comparable deals',
    audience: 'partner',
  },
  {
    id: 'deal-terms',
    label: 'Deal Terms',
    hint: 'what was negotiated across a set',
    audience: 'partner',
  },
  {
    id: 'coverage',
    label: 'Coverage',
    hint: 'where experience is thick or thin',
    audience: 'km',
  },
  {
    id: 'semantic-layer',
    label: 'Semantic Layer',
    hint: 'how a question becomes a number',
    audience: 'engineer',
  },
  {
    id: 'tables',
    label: 'Tables',
    hint: 'browse the raw data',
    audience: 'operator',
  },
  {
    id: 'admin',
    label: 'Admin',
    hint: 'ingest, calibration, evals, logs',
    audience: 'operator',
  },
  {
    id: 'label',
    label: 'Label',
    hint: 'review the uncertainty queue',
    audience: 'km',
  },
] as const

export const SHORTCUTS: ReadonlyArray<[string, string]> = [
  ['1 – 8', 'switch tab'],
  ['/', 'focus search'],
  ['j / k', 'move through results'],
  ['Enter', 'open the focused result'],
  ['?', 'show this help'],
  ['Esc', 'close / clear'],
]
