/**
 * The six tabs, in demo order. Explore is first because it is the entry point for demo
 * script 1 and the only view a partner would open unprompted.
 *
 * Order is load-bearing: the number-key shortcut is the index, so reordering this array
 * silently rebinds every shortcut.
 */
export type TabId = 'explore' | 'deal-terms' | 'coverage' | 'tables' | 'admin' | 'label'

export interface Tab {
  id: TabId
  label: string
  hint: string
  audience: 'partner' | 'km' | 'operator'
}

export const TABS: readonly Tab[] = [
  { id: 'explore', label: 'Explore', hint: 'find comparable deals', audience: 'partner' },
  { id: 'deal-terms', label: 'Deal Terms', hint: 'what was negotiated across a set', audience: 'partner' },
  { id: 'coverage', label: 'Coverage', hint: 'where experience is thick or thin', audience: 'km' },
  { id: 'tables', label: 'Tables', hint: 'browse the raw data', audience: 'operator' },
  { id: 'admin', label: 'Admin', hint: 'ingest, calibration, evals, logs', audience: 'operator' },
  { id: 'label', label: 'Label', hint: 'review the uncertainty queue', audience: 'km' },
] as const

export const SHORTCUTS: ReadonlyArray<[string, string]> = [
  ['1 – 6', 'switch tab'],
  ['/', 'focus search'],
  ['j / k', 'move through results'],
  ['Enter', 'open the focused result'],
  ['?', 'show this help'],
  ['Esc', 'close / clear'],
]
