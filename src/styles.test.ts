import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const styles = readFileSync('src/styles.css', 'utf8')

function token(name: string): string {
  const tokens = Object.fromEntries(
    [...styles.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((match) => [match[1], match[2]]),
  )
  if (!tokens[name]) throw new Error(`Missing color token --${name}`)
  return tokens[name]
}

function luminance(hex: string): number {
  const channels = hex.slice(1).match(/.{2}/g)!.map((value) => {
    const normalized = Number.parseInt(value, 16) / 255
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
  })
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (light + 0.05) / (dark + 0.05)
}

describe('calm blue palette contrast', () => {
  it.each([
    ['ink', 'paper', 7],
    ['ink-soft', 'paper', 4.5],
    ['ink-faint', 'surface', 4.5],
    ['brand', 'surface', 4.5],
    ['green-ink', 'green-soft', 4.5],
    ['amber-ink', 'amber-soft', 4.5],
    ['red-ink', 'red-soft', 4.5],
  ])('%s on %s meets the expected WCAG contrast', (foreground, background, minimum) => {
    expect(contrast(token(foreground), token(background))).toBeGreaterThanOrEqual(minimum)
  })

  it('keeps white text on the primary blue button above WCAG AA', () => {
    expect(contrast(token('brand'), '#ffffff')).toBeGreaterThanOrEqual(4.5)
  })
})