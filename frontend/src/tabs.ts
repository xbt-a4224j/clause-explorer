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
 * #54 replaced Admin with Trust rather than adding a seventh tab. Admin split along a real
 * line: the evidence — calibration, the label loop, selection quality — is what a reader
 * comes for and became Trust; the operator surface (ingest status, the log viewer) folds
 * into a collapsed section at the bottom of it. Six tabs before, six after.
 *
 * Ask sits second, behind Overview. It was called Semantic Layer, which named the mechanism
 * rather than the act; the semantic-layer argument still lives inside it, below the
 * demonstration rather than in front of it.
 *
 * Order is load-bearing: the number-key shortcut is the index, so reordering this array
 * silently rebinds every shortcut. `TAB_IDS`'s order is the one the platform's `Shell`
 * actually renders from (semantic-explorer-base#8); this array stays as the labeled,
 * grouped view of the same six ids that this app's own code and tests read.
 */
// Ids come from the platform. `terms` was `deal-terms`, which shipped into a health-claims
// fork of this app and stayed there: an id lives in URLs, tests and keyboard bindings, so it
// outlives the label somebody remembered to rename. The id is the part nobody thinks to
// change, which is why it is the part that has to be generic — the LABEL below is still
// "Deal Terms", because this is a legal product and should read like one.
export type { TabId } from '@semantic-explorer-base/ui'
import { EVIDENCE_TAB_IDS, TAB_IDS } from '@semantic-explorer-base/ui'
import type { TabId } from '@semantic-explorer-base/ui'

import { STRINGS } from './strings'

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
   *
   * Membership comes from the platform's `EVIDENCE_TAB_IDS` rather than being repeated here —
   * this used to hardcode the same split a second time, and a domain editing this array had no
   * way to know it was also supposed to agree with the platform's own copy.
   */
  group: 'work' | 'under-the-hood'
}

const AUDIENCE: Record<TabId, Tab['audience']> = {
  overview: 'partner',
  ask: 'partner',
  explore: 'partner',
  terms: 'partner',
  trust: 'km',
  label: 'km',
}

export const TABS: readonly Tab[] = TAB_IDS.map((id) => ({
  id,
  audience: AUDIENCE[id],
  group: EVIDENCE_TAB_IDS.has(id) ? 'under-the-hood' : 'work',
  ...STRINGS.tabs[id],
}))

export const SHORTCUTS: ReadonlyArray<[string, string]> = [
  ['1 – 6', 'switch tab'],
  // On Explore this is Explore's own box; on every other tab it is the header box, which now
  // carries what you type to Explore rather than swallowing it.
  ['/', 'focus search — Enter searches Explore'],
  ['j / k', 'move through results'],
  ['Enter', 'open the focused result'],
  ['?', 'show this help'],
  ['Esc', 'close / clear'],
]
