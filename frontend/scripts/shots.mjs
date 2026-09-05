// Annotated screenshots for README + walkthrough.
// Run from frontend/ with the app on :5173 and the API up:  node scripts/shots.mjs
// Callouts are located by CSS selector and drawn in-page as an SVG overlay (red ring +
// numbered caption), so the whole set regenerates after any UI change. Missing selectors are
// skipped with a warning rather than failing the run. Each shot is clipped to the region that
// contains its callouts, so the explainer prose above the tool never fills the frame.

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const BASE = process.env.SHOTS_BASE ?? 'http://localhost:5173'
const OUT = resolve(import.meta.dirname, '../../docs/img')
mkdirSync(OUT, { recursive: true })

const VIEW = { width: 1440, height: 900 }

const SHOTS = [
  {
    name: 'overview',
    tab: 'Overview',
    collapse: false,
    callouts: [
      { sel: '.shell__tabgroup', text: 'the bar splits: the product, then the evidence' },
      { sel: '.jrn__who', text: 'each journey names who is asking' },
      { sel: '.jrn__run', text: 'lands on the first step, already filtered' },
    ],
  },
  {
    name: 'explore',
    tab: 'Explore',
    before: async (page) => {
      await page.fill('.explore__input', 'healthcare')
      // wait for real rows, not the skeleton: a debounce plus two round trips means a fixed
      // timeout screenshots the loading state about half the time
      await page.waitForFunction(
        () => document.querySelectorAll('.explore__list li').length > 3,
        { timeout: 20000 },
      )
      await page.waitForTimeout(300)
    },
    callouts: [
      { sel: '.explore__input', text: 'describe the deal in plain words' },
      { sel: '.explore__resolved', text: 'resolved to a FOLIO code, not a display label' },
      { sel: '.facet__value', text: 'facet counts recompute against what is left' },
      { sel: '.facet__unavailable', text: 'empty values stay visible, disabled: absence is information' },
    ],
  },
  {
    name: 'deal-terms',
    tab: 'Deal Terms',
    callouts: [
      { sel: '.terms__caption', text: 'counts, not percentages, below n=30' },
      { sel: '.term__figures', text: 'how many of the set answered this point' },
      { sel: '.term__positions', text: 'the distribution, each position with its n' },
    ],
  },
  {
    name: 'deal-terms-drill',
    tab: 'Deal Terms',
    before: async (page) => {
      await page
        .locator('li', { has: page.locator('.term__name', { hasText: 'Fiduciary exception' }) })
        .locator('.term__hit')
        .first()
        .click()
      await page.waitForSelector('.term__drill', { timeout: 10000 })
      await page.waitForTimeout(400)
    },
    callouts: [
      { sel: '[data-testid="excerpt-note"]', text: "MAUD's span is document-scale: said plainly, not passed off as the clause" },
      { sel: '.dp__span', text: 'the file and the character range it came from' },
    ],
  },
  // The 'coverage' shot went with the Coverage tab in #48. Its argument — a gap is shown, not
  // smoothed — is called out on the Explore shot above, which is now the only surface making it.
  {
    name: 'semantic-layer',
    tab: 'Ask',
    callouts: [
      { sel: '.cat__list', text: 'the vocabulary the model may select from, read live from Cube' },
      { sel: '.qb__json', text: 'its output: a selection, never SQL. Gradeable offline' },
    ],
  },
  {
    name: 'refusal',
    tab: 'Ask',
    before: async (page) => {
      await page.locator('.qb__example', { hasText: 'refused' }).first().click()
      await page.waitForTimeout(300)
      await page.locator('.qb__run').click()
      await page.waitForSelector('[data-testid="qb-refused"]', { timeout: 10000 })
    },
    callouts: [
      { sel: '.qb__json', text: 'the selection that was sent' },
      { sel: '[data-testid="qb-refused"]', text: "min_n refusal: filter to one deal and you have one client's term" },
    ],
  },
  {
    name: 'label',
    tab: 'Label',
    before: async (page) => {
      // the queue grew from 100 items to 1,701 when #44 calibrated the full vocabulary, so the
      // tab now takes ~2.6s to paint and a fixed wait screenshots an empty state
      await page.waitForSelector('.label__item', { timeout: 30000 })
      await page.waitForTimeout(300)
    },
    callouts: [
      { sel: '.label__disagree', text: 'two extractors disagree, so one is wrong: ranked first' },
      { sel: '.label__predictions', text: 'model vs keyword baseline, side by side' },
      { sel: '.label__hint', text: 'keyboard only: y accept · n correct · e edit · s skip' },
      { sel: '.label__progress', text: 'decisions are graded into the next calibration run' },
    ],
  },
  {
    name: 'admin-calibration',
    tab: 'Admin',
    callouts: [
      { sel: '[data-testid="calibration-report"]', text: 'accuracy per deal point on held-out gold, published not buried' },
    ],
  },
]

const OVERLAY_ID = '__shots_overlay'

/** Collapse every open explainer panel on the current tab so the tool is what gets framed. */
async function collapseExplainers(page) {
  const toggles = page.locator('.explain__toggle[aria-expanded="true"]')
  const n = await toggles.count()
  for (let i = 0; i < n; i++) await toggles.nth(i).click()
  if (n) await page.waitForTimeout(200)
}

/** Absolute page-coordinate boxes, measured without scrolling so they are mutually consistent. */
async function measure(page, callouts) {
  const boxes = []
  for (const c of callouts) {
    const loc = page.locator(c.sel).first()
    if ((await loc.count()) === 0) {
      console.warn(`  skip: ${c.sel} not found`)
      continue
    }
    const b = await loc.evaluate((el) => {
      const r = el.getBoundingClientRect()
      const text = (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement ? el.value : (el.innerText ?? el.textContent ?? '')).trim()
      return { x: r.left + window.scrollX, y: r.top + window.scrollY, width: r.width, height: r.height, text }
    })
    if (b.width === 0 || b.height === 0 || (b.text === '' && !c.allowEmpty)) {
      console.warn(`  skip: ${c.sel} has no box or no text`)
      continue
    }
    boxes.push({ ...b, text: c.text })
  }
  return boxes
}

async function drawOverlay(page, boxes) {
  await page.evaluate(
    ({ boxes, id }) => {
      document.getElementById(id)?.remove()
      const W = document.documentElement.scrollWidth
      const H = document.documentElement.scrollHeight
      const ns = 'http://www.w3.org/2000/svg'
      const svg = document.createElementNS(ns, 'svg')
      svg.id = id
      svg.setAttribute('width', W)
      svg.setAttribute('height', H)
      Object.assign(svg.style, {
        position: 'absolute',
        left: '0',
        top: '0',
        pointerEvents: 'none',
        zIndex: '99999',
        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      })
      const RED = '#c0392b'
      const mk = (tag, attrs) => {
        const e = document.createElementNS(ns, tag)
        for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v))
        return e
      }
      boxes.forEach((b, i) => {
        const pad = 8
        const compact = b.width < 480 && b.height < 110 && b.width / Math.max(b.height, 1) <= 4
        let ring
        if (!compact) {
          ring = mk('rect', {
            x: b.x - pad,
            y: b.y - pad,
            width: b.width + 2 * pad,
            height: b.height + 2 * pad,
            rx: 14,
          })
        } else {
          ring = mk('ellipse', {
            cx: b.x + b.width / 2,
            cy: b.y + b.height / 2,
            rx: b.width / 2 + pad + 6,
            ry: Math.max(b.height / 2 + pad + 4, 16),
          })
        }
        ring.setAttribute('fill', 'none')
        ring.setAttribute('stroke', RED)
        ring.setAttribute('stroke-width', '3')
        svg.appendChild(ring)

        // caption sits just below the ring, left-aligned with it, clamped to the page
        const fw = Math.min(b.text.length * 7.4 + 40, 620)
        const fh = 30
        let lx = b.x + b.width + pad + 12
        let ly = b.y + b.height / 2 - fh / 2
        if (lx + fw > W - 8) {
          lx = b.x - pad
          ly = b.y + b.height + pad + 8
          if (lx + fw > W - 8) lx = W - 8 - fw
        }
        if (lx < 8) lx = 8
        if (ly + fh > H - 8) ly = b.y - pad - fh - 8
        const g = document.createElementNS(ns, 'g')
        const rect = mk('rect', { x: lx, y: ly, width: fw, height: fh, rx: 4, fill: '#fff', stroke: RED, 'stroke-width': 2 })
        const badge = mk('circle', { cx: lx + 15, cy: ly + fh / 2, r: 10, fill: RED })
        const num = mk('text', {
          x: lx + 15,
          y: ly + fh / 2 + 4.5,
          'text-anchor': 'middle',
          fill: '#fff',
          'font-size': 13,
          'font-weight': 700,
        })
        num.textContent = String(i + 1)
        const txt = mk('text', { x: lx + 32, y: ly + fh / 2 + 4.5, fill: '#1a1a1a', 'font-size': 13 })
        txt.textContent = b.text
        g.append(rect, badge, num, txt)
        svg.appendChild(g)
      })
      document.body.appendChild(svg)
    },
    { boxes, id: OVERLAY_ID },
  )
}

/** Clip to the region holding every callout (plus room for captions), never taller than the viewport. */
function clipFor(boxes, pageHeight) {
  const top = Math.min(...boxes.map((b) => b.y)) - 24
  const bottom = Math.max(...boxes.map((b) => b.y + b.height)) + 64
  const height = Math.min(Math.max(bottom - top, 320), VIEW.height)
  const y = Math.max(0, Math.min(top, pageHeight - height))
  return { x: 0, y, width: VIEW.width, height }
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: VIEW, deviceScaleFactor: 2 })
await page.goto(BASE, { waitUntil: 'networkidle' })

for (const shot of SHOTS) {
  console.log(`▸ ${shot.name}`)
  await page.getByRole('tab', { name: shot.tab }).click()
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(600)
  if (shot.collapse !== false) await collapseExplainers(page)
  try {
    if (shot.before) await shot.before(page)
  } catch (e) {
    console.warn(`  before() failed: ${e.message.split('\n')[0]}`)
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  const boxes = await measure(page, shot.callouts)
  if (boxes.length === 0) {
    console.warn('  nothing to frame, skipped')
    continue
  }
  await drawOverlay(page, boxes)
  const pageHeight = await page.evaluate(() => document.documentElement.scrollHeight)
  const clip = clipFor(boxes, pageHeight)
  await page.screenshot({ path: `${OUT}/${shot.name}.png`, fullPage: true, clip })
  await page.evaluate((id) => document.getElementById(id)?.remove(), OVERLAY_ID)
  console.log(`  ${boxes.length}/${shot.callouts.length} callouts → docs/img/${shot.name}.png`)
}

await browser.close()
