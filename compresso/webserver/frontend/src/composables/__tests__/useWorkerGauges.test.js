import { describe, it, expect, vi } from 'vitest'

// Mock quasar before importing
vi.mock('quasar', () => ({
  useQuasar: () => ({
    dark: { isActive: false },
  }),
}))

import { useWorkerGauges } from '../useWorkerGauges'

describe('useWorkerGauges', () => {
  const { clampPercent, formatPercent, gradientColor, generateGroupColour } = useWorkerGauges()

  describe('clampPercent', () => {
    it('clamps values above 100 to 100', () => {
      expect(clampPercent(150)).toBe(100)
    })

    it('clamps values below 0 to 0', () => {
      expect(clampPercent(-10)).toBe(0)
    })

    it('returns 0 for NaN', () => {
      expect(clampPercent(NaN)).toBe(0)
    })

    it('returns 0 for Infinity', () => {
      expect(clampPercent(Infinity)).toBe(0)
    })

    it('passes through valid values', () => {
      expect(clampPercent(50)).toBe(50)
      expect(clampPercent(0)).toBe(0)
      expect(clampPercent(100)).toBe(100)
    })
  })

  describe('formatPercent', () => {
    it('rounds to 2 decimal places', () => {
      expect(formatPercent(33.3333)).toBe(33.33)
    })

    it('handles whole numbers', () => {
      expect(formatPercent(50)).toBe(50)
    })

    it('handles zero', () => {
      expect(formatPercent(0)).toBe(0)
    })
  })

  describe('gradientColor', () => {
    it('returns an rgb string', () => {
      const result = gradientColor(50)
      expect(result).toMatch(/^rgb\(\d+, \d+, \d+\)$/)
    })

    it('returns different colors for 0% and 100%', () => {
      const low = gradientColor(0)
      const high = gradientColor(100)
      expect(low).not.toBe(high)
    })
  })

  describe('generateGroupColour', () => {
    it('returns a hex color string', () => {
      const result = generateGroupColour('test-group')
      expect(result).toMatch(/^#[0-9a-f]{6}$/i)
    })

    it('is deterministic', () => {
      const a = generateGroupColour('my-group')
      const b = generateGroupColour('my-group')
      expect(a).toBe(b)
    })

    it('returns different colors for different inputs', () => {
      const a = generateGroupColour('group-a')
      const b = generateGroupColour('group-b')
      expect(a).not.toBe(b)
    })
  })
})
