/**
 * Colour lives in tokens.css. This fails the build if a hex escapes into a component.
 *
 * CLAUDE.md claimed two hardcoded hexes in the codebase; a survey for #63 found nineteen.
 * Eleven were promoted to tokens in e80d5b1. A claim in a document is worth nothing next to a
 * check that runs, which is the whole reason this file exists rather than another paragraph.
 *
 * It judges CODE, not prose. `charts.tsx` documents the palette-validation command and the six
 * values it passed on — `"#2a78d6,#eb6834" --mode light --surface #ffffff → all six PASS` — and
 * that provenance is the most valuable comment in the file. A test that banned it would be
 * silenced within a week. So comments are stripped before the grep, the same distinction the
 * platform's import-boundary test makes.
 *
 * Sources come from `import.meta.glob`, not `node:fs`. The first version read the filesystem,
 * which vitest ran happily and `tsc --noEmit` rejected: the app's tsconfig types browser code
 * and carries no node builtins. Adding @types/node to satisfy one lint test would be a
 * dependency bought for a check that can avoid needing it — and this way the test sees exactly
 * the files Vite bundles. `vite/client` is in tsconfig `types` for the same reason: vite is
 * already a dependency, so the glob costs nothing new.
 *
 * Only the TS/TSX sources are read. tokens.css is deliberately not asserted on: Vite's CSS
 * pipeline does not return raw text for it under `?raw` in the test environment, and the
 * emptiness guard below already stops this suite passing vacuously.
 */
import { describe, expect, it } from 'vitest'

const SOURCES = import.meta.glob('./**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Block and line comments removed, so documented provenance is not mistaken for a colour. */
function codeOnly(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
}

const HEX = /#[0-9a-fA-F]{3,8}\b/g

const components = Object.entries(SOURCES).filter(([path]) => !/\.test\.tsx?$/.test(path))

describe('colour comes from tokens.css', () => {
  it('finds the components to check', () => {
    // Guards against the whole suite passing vacuously: a glob that matched nothing would make
    // every assertion below trivially true, which is the failure mode of every grep-style test.
    expect(components.length).toBeGreaterThan(10)
  })

  it.each(components)('%s has no hardcoded hex', (_path, source) => {
    expect(codeOnly(source).match(HEX) ?? []).toEqual([])
  })

})

describe('the platform UI is present and is the source of colour', () => {
  const VENDORED = import.meta.glob('../vendor/semantic-explorer-base-ui/src/**/*.css', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>

  // Only the PRESENCE of the vendored files is checked here. Asserting their CONTENT was
  // tried and does not work: Vite's CSS pipeline returns empty text under `?raw` in the test
  // environment, the same limitation that removed the local tokens.css assertion above. The
  // palette's contents — including the mechanism colours — are asserted in the platform's own
  // suite, where the file is read from disk and the check actually runs.
  it('the sync actually ran', () => {
    // A missing vendor/ resolves the alias to nothing and fails the build — but only the
    // BUILD, and only once someone runs it. This says so in the test suite instead, because
    // "did you run make platform-sync" is a question worth answering in a second.
    expect(Object.keys(VENDORED).length).toBeGreaterThan(0)
  })

})
