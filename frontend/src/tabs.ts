/**
 * The six tabs, in demo order. Overview is first and is the landing tab (#39): every
 * other view assumes you already know what the system is, and a visitor who starts on
 * Explore sees a faceted search without ever learning that retrieval is hybrid or that
 * aggregate figures come from a governed semantic layer rather than from generation.
 *
 * #48 cut two. Coverage answered "where is our experience thick or thin", a knowledge-
 * management question rather than "what is market", and its one durable idea — that a gap
 * is a finding — is demonstrated on Explore, where zero-count facet values stay visible and
 * disabled with the reason stated. Tables existed so nobody had to open psql, which is a
 * convenience for whoever operates the thing and the surface most likely to make a reader
 * conclude this is a database browser with extra steps.
 *
 * Ask sits second, behind Overview. It was called Semantic Layer, which named the mechanism
 * rather than the act; the semantic-layer argument still lives inside it, below the
 * demonstration rather than in front of it.
 *
 * Order is load-bearing: the number-key shortcut is the index, so reordering this array
 * silently rebinds every shortcut.
 */
export type TabId = 'overview' | 'ask' | 'explore' | 'deal-terms' | 'admin' | 'label'

export interface Tab {
  id: TabId
  label: string
  hint: string
  audience: 'partner' | 'km' | 'operator' | 'engineer'
  /**
   * Which half of the tab bar this sits in. `work` is the product an analyst uses to answer a
   * question; `under-the-hood` is the evidence that the answers are trustworthy. Eight
   * undifferentiated tabs read as a feature list and hide which three someone would actually
   * open, so the bar is split and the second group is styled quieter.
   */
  group: 'work' | 'under-the-hood'
}

export const TABS: readonly Tab[] = [
  {
    id: 'overview',
    label: 'Overview',
    hint: 'what this is and how it works',
    audience: 'partner',
    group: 'work',
  },
  {
    id: 'ask',
    label: 'Ask',
    hint: 'a question becomes a governed number, or a refusal',
    audience: 'partner',
    group: 'work',
  },
  {
    id: 'explore',
    label: 'Explore',
    hint: 'find comparable deals',
    audience: 'partner',
    group: 'work',
  },
  {
    id: 'deal-terms',
    label: 'Deal Terms',
    hint: 'what was negotiated across a set',
    audience: 'partner',
    group: 'work',
  },
  {
    id: 'admin',
    label: 'Admin',
    hint: 'ingest, calibration, evals, logs',
    audience: 'operator',
    group: 'under-the-hood',
  },
  {
    id: 'label',
    label: 'Label',
    hint: 'review the uncertainty queue',
    audience: 'km',
    group: 'under-the-hood',
  },
] as const

export const SHORTCUTS: ReadonlyArray<[string, string]> = [
  ['1 – 6', 'switch tab'],
  ['/', 'focus search'],
  ['j / k', 'move through results'],
  ['Enter', 'open the focused result'],
  ['?', 'show this help'],
  ['Esc', 'close / clear'],
]
