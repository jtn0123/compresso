import { describe, it, expect, vi } from 'vitest'

vi.mock('src/js/compressoTheme', () => ({
  getChartColors: vi.fn(() => ['#aa0000', '#bb0000', '#cc0000']),
  getChartColor: vi.fn((index) => `#chart${index}`),
}))

import { useChartTheme } from '../useChartTheme'

describe('useChartTheme', () => {
  const { getChartColors, getChartColor, chartBgColor } = useChartTheme()

  describe('getChartColors', () => {
    it('delegates to compressoTheme', () => {
      const result = getChartColors()
      expect(result).toEqual(['#aa0000', '#bb0000', '#cc0000'])
    })
  })

  describe('getChartColor', () => {
    it('delegates to compressoTheme with index', () => {
      const result = getChartColor(2)
      expect(result).toBe('#chart2')
    })
  })

  describe('chartBgColor', () => {
    it('appends hex alpha for 0.1 opacity', () => {
      const result = chartBgColor(1, 0.1)
      // 0.1 * 255 = 25.5, rounds to 26 = 0x1a
      expect(result).toBe('#chart11a')
    })

    it('appends hex alpha for 0.5 opacity', () => {
      const result = chartBgColor(1, 0.5)
      // 0.5 * 255 = 127.5, rounds to 128 = 0x80
      expect(result).toBe('#chart180')
    })

    it('appends hex alpha for 1.0 opacity', () => {
      const result = chartBgColor(1, 1.0)
      // 1.0 * 255 = 255 = 0xff
      expect(result).toBe('#chart1ff')
    })

    it('appends hex alpha for 0 opacity', () => {
      const result = chartBgColor(1, 0)
      // 0 * 255 = 0 = 0x00
      expect(result).toBe('#chart100')
    })

    it('defaults to 0.1 alpha when not specified', () => {
      const result = chartBgColor(1)
      expect(result).toBe('#chart11a')
    })
  })
})
