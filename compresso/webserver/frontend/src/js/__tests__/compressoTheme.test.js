import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockSetCssVar = vi.fn()

vi.mock('quasar', () => ({
  setCssVar: (...args) => mockSetCssVar(...args),
}))

import {
  PALETTES,
  applyTheme,
  getChartColors,
  getChartColor,
  getPaletteNames,
  getPalettePreview,
} from '../compressoTheme'

const HEX_RE = /^#[0-9a-fA-F]{6}$/

const REQUIRED_VARIANT_KEYS = [
  'primary', 'secondary', 'accent', 'warning',
  'primarySoft', 'primaryBorder',
  'surface0', 'surface1', 'surface2', 'surfaceRaised',
  'headerBg', 'headerGradientEnd',
  'chart',
]

describe('PALETTES', () => {
  it('has forest and ember palettes', () => {
    expect(PALETTES).toHaveProperty('forest')
    expect(PALETTES).toHaveProperty('ember')
  })

  it.each(['forest', 'ember'])('%s has light and dark variants', (palette) => {
    expect(PALETTES[palette]).toHaveProperty('light')
    expect(PALETTES[palette]).toHaveProperty('dark')
  })

  it.each(['forest', 'ember'])('%s variants have all required keys', (palette) => {
    for (const mode of ['light', 'dark']) {
      const variant = PALETTES[palette][mode]
      for (const key of REQUIRED_VARIANT_KEYS) {
        expect(variant, `${palette}.${mode} missing '${key}'`).toHaveProperty(key)
      }
    }
  })

  it.each(['forest', 'ember'])('%s chart arrays have exactly 10 colors', (palette) => {
    for (const mode of ['light', 'dark']) {
      expect(PALETTES[palette][mode].chart).toHaveLength(10)
    }
  })

  it.each(['forest', 'ember'])('%s color values are valid hex strings', (palette) => {
    for (const mode of ['light', 'dark']) {
      const v = PALETTES[palette][mode]
      for (const key of ['primary', 'secondary', 'accent', 'warning', 'primarySoft', 'primaryBorder', 'headerBg', 'headerGradientEnd']) {
        expect(v[key], `${palette}.${mode}.${key}`).toMatch(HEX_RE)
      }
      for (const color of v.chart) {
        expect(color).toMatch(HEX_RE)
      }
    }
  })
})

describe('applyTheme', () => {
  let setPropertySpy
  let setAttributeSpy

  beforeEach(() => {
    vi.clearAllMocks()
    setPropertySpy = vi.spyOn(document.body.style, 'setProperty')
    setAttributeSpy = vi.spyOn(document.body, 'setAttribute')
  })

  it('calls setCssVar for primary, secondary, accent, warning', () => {
    applyTheme('light', 'forest')
    const calls = mockSetCssVar.mock.calls.map(c => c[0])
    expect(calls).toContain('primary')
    expect(calls).toContain('secondary')
    expect(calls).toContain('accent')
    expect(calls).toContain('warning')
  })

  it('sets correct primary color for forest light', () => {
    applyTheme('light', 'forest')
    expect(mockSetCssVar).toHaveBeenCalledWith('primary', '#1a6b4a')
  })

  it('sets correct primary color for ember dark', () => {
    applyTheme('dark', 'ember')
    expect(mockSetCssVar).toHaveBeenCalledWith('primary', '#e07030')
  })

  it('sets extended CSS vars on document.body.style', () => {
    applyTheme('light', 'forest')
    const propNames = setPropertySpy.mock.calls.map(c => c[0])
    expect(propNames).toContain('--compresso-primary-soft')
    expect(propNames).toContain('--compresso-primary-border')
    expect(propNames).toContain('--compresso-header-bg')
    expect(propNames).toContain('--compresso-header-gradient-end')
  })

  it('sets surface hierarchy vars', () => {
    applyTheme('dark', 'forest')
    const propNames = setPropertySpy.mock.calls.map(c => c[0])
    expect(propNames).toContain('--surface-0')
    expect(propNames).toContain('--surface-1')
    expect(propNames).toContain('--surface-2')
  })

  it('sets 10 chart color CSS vars', () => {
    applyTheme('light', 'ember')
    const chartProps = setPropertySpy.mock.calls
      .map(c => c[0])
      .filter(name => name.startsWith('--compresso-chart-'))
    expect(chartProps).toHaveLength(10)
  })

  it('sets data-palette attribute on body', () => {
    applyTheme('light', 'ember')
    expect(setAttributeSpy).toHaveBeenCalledWith('data-palette', 'ember')
  })

  it('sets --q-card-head for backward compat', () => {
    applyTheme('light', 'forest')
    const cardHeadCall = setPropertySpy.mock.calls.find(c => c[0] === '--q-card-head')
    expect(cardHeadCall).toBeTruthy()
    expect(cardHeadCall[1]).toBe(PALETTES.forest.light.surfaceRaised)
  })

  it('falls back to forest.light for unknown palette', () => {
    applyTheme('light', 'nonexistent')
    expect(mockSetCssVar).toHaveBeenCalledWith('primary', PALETTES.forest.light.primary)
  })

  it('falls back to forest.light for unknown mode', () => {
    applyTheme('invalid', 'forest')
    expect(mockSetCssVar).toHaveBeenCalledWith('primary', PALETTES.forest.light.primary)
  })
})

describe('getChartColors', () => {
  it('returns array of 10 strings', () => {
    // Set up chart vars first
    applyTheme('light', 'forest')
    const colors = getChartColors()
    expect(colors).toHaveLength(10)
    colors.forEach(c => expect(typeof c).toBe('string'))
  })
})

describe('getChartColor', () => {
  it('returns a single color string by index', () => {
    applyTheme('light', 'forest')
    const color = getChartColor(1)
    expect(typeof color).toBe('string')
    expect(color.length).toBeGreaterThan(0)
  })
})

describe('getPaletteNames', () => {
  it('returns forest and ember', () => {
    expect(getPaletteNames()).toEqual(['forest', 'ember'])
  })
})

describe('getPalettePreview', () => {
  it('returns light/dark primary/secondary for valid palette', () => {
    const preview = getPalettePreview('forest')
    expect(preview).toHaveProperty('light')
    expect(preview).toHaveProperty('dark')
    expect(preview.light).toHaveProperty('primary')
    expect(preview.light).toHaveProperty('secondary')
    expect(preview.dark).toHaveProperty('primary')
    expect(preview.dark).toHaveProperty('secondary')
  })

  it('returns null for unknown palette', () => {
    expect(getPalettePreview('nonexistent')).toBeNull()
  })

  it('returns correct colors', () => {
    const preview = getPalettePreview('ember')
    expect(preview.light.primary).toBe(PALETTES.ember.light.primary)
    expect(preview.dark.secondary).toBe(PALETTES.ember.dark.secondary)
  })
})
