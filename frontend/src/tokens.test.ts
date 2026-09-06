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
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = dirname(fileURLToPath(import.meta.url))

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return sources(full)
    return /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [full] : []
  })
}

/** Block comments, line comments and string literals that are import paths. */
function codeOnly(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
}

const HEX = /#[0-9a-fA-F]{3,8}\b/g

describe('colour comes from tokens.css', () => {
  const files = sources(SRC)

  it('finds the components to check', () => {
    expect(files.length).toBeGreaterThan(10)
  })

  it.each(files.map((f) => [f.slice(SRC.length + 1), f]))('%s has no hardcoded hex', (_name, path) => {
    const found = codeOnly(readFileSync(path, 'utf8')).match(HEX) ?? []
    expect(found).toEqual([])
  })

  it('the token file itself is where the hexes are', () => {
    const tokens = readFileSync(join(SRC, 'styles/tokens.css'), 'utf8')
    expect((tokens.match(HEX) ?? []).length).toBeGreaterThan(20)
  })
})
