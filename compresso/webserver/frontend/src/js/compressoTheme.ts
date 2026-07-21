/**
 * Compresso Theme System
 *
 * Manages two color palettes (Forest, Ember) each with light and dark variants.
 * All colors are applied via CSS custom properties for runtime switching.
 */
import { setCssVar } from 'quasar'

const PALETTES = {
  forest: {
    light: {
      primary: '#1a6b4a',
      secondary: '#d49a1e',
      accent: '#7c5cbf',
      warning: '#d49a1e',
      positive: '#2e9e5a',
      negative: '#d43545',
      info: '#3a8fd4',
      primarySoft: '#e6f2ec',
      primaryBorder: '#b3d4c4',
      surface0: '#f5f6f7',
      surface1: '#ffffff',
      surface2: '#f8f9fa',
      surfaceRaised: '#f0f3f1',
      sidebarBg: '#fbfcfc',
      headerBg: '#13291f',
      headerGradientEnd: '#1a3d2d',
      chart: [
        '#1a6b4a',
        '#d49a1e',
        '#7c5cbf',
        '#d43545',
        '#2e9e5a',
        '#3a8fd4',
        '#e67e22',
        '#1abc9c',
        '#34495e',
        '#95a5a6',
      ],
    },
    dark: {
      primary: '#2fb27f',
      secondary: '#e8a525',
      accent: '#a08ad8',
      warning: '#e8a525',
      positive: '#34b46f',
      negative: '#e05563',
      info: '#58a6e8',
      primarySoft: '#1a2a28',
      primaryBorder: '#215644',
      surface0: '#0e0f11',
      surface1: '#17181c',
      surface2: '#1d1f24',
      surfaceRaised: '#1d1f24',
      sidebarBg: '#141519',
      headerBg: '#0e0f11',
      headerGradientEnd: '#0e0f11',
      chart: [
        '#2fb27f',
        '#e8a525',
        '#a08ad8',
        '#e05563',
        '#34b46f',
        '#58a6e8',
        '#f0a050',
        '#40d8b0',
        '#8898a8',
        '#b0b8c0',
      ],
    },
  },
  ember: {
    light: {
      primary: '#c05621',
      secondary: '#4a6670',
      accent: '#8b6f47',
      warning: '#c05621',
      positive: '#2e9e5a',
      negative: '#d43545',
      info: '#3a8fd4',
      primarySoft: '#fdf0e8',
      primaryBorder: '#f0c9a8',
      surface0: '#f6f5f4',
      surface1: '#ffffff',
      surface2: '#faf8f7',
      surfaceRaised: '#f3f1ef',
      sidebarBg: '#fcfbfa',
      headerBg: '#2c2017',
      headerGradientEnd: '#3d2e22',
      chart: [
        '#c05621',
        '#4a6670',
        '#8b6f47',
        '#d43545',
        '#2e9e5a',
        '#3a8fd4',
        '#b8512e',
        '#1abc9c',
        '#5d4e37',
        '#95a5a6',
      ],
    },
    dark: {
      primary: '#e07030',
      secondary: '#7a9aa8',
      accent: '#b8965e',
      warning: '#e07030',
      positive: '#34b46f',
      negative: '#e05563',
      info: '#58a6e8',
      primarySoft: '#2f231e',
      primaryBorder: '#673b24',
      surface0: '#0e0f11',
      surface1: '#17181c',
      surface2: '#1d1f24',
      surfaceRaised: '#1d1f24',
      sidebarBg: '#141519',
      headerBg: '#0e0f11',
      headerGradientEnd: '#0e0f11',
      chart: [
        '#e07030',
        '#7a9aa8',
        '#b8965e',
        '#e05563',
        '#34b46f',
        '#58a6e8',
        '#f0a050',
        '#40d8b0',
        '#8898a8',
        '#b0b8c0',
      ],
    },
  },
} as const

export type ThemeMode = 'light' | 'dark'
export type PaletteName = keyof typeof PALETTES

export const isThemeMode = (value: unknown): value is ThemeMode => value === 'light' || value === 'dark'

// Derived from PALETTES so adding a palette is a one-place change
export const isPaletteName = (value: unknown): value is PaletteName => typeof value === 'string' && value in PALETTES

/**
 * Apply a theme (mode + palette) to the application.
 * Sets all Quasar and custom CSS variables.
 *
 * @param {'light'|'dark'} mode
 * @param {'forest'|'ember'} palette
 */
export function applyTheme(mode: ThemeMode | string, palette: PaletteName | string): void {
  const paletteConfig = isPaletteName(palette) ? PALETTES[palette] : undefined
  const p = paletteConfig && isThemeMode(mode) ? paletteConfig[mode] : PALETTES.forest.light

  // Quasar built-in CSS vars
  setCssVar('primary', p.primary)
  setCssVar('secondary', p.secondary)
  setCssVar('accent', p.accent)
  setCssVar('warning', p.warning)
  if (p.positive) setCssVar('positive', p.positive)
  if (p.negative) setCssVar('negative', p.negative)
  if (p.info) setCssVar('info', p.info)

  // Extended Compresso CSS vars
  const body = document.body.style
  body.setProperty('--compresso-primary-soft', p.primarySoft)
  body.setProperty('--compresso-primary-border', p.primaryBorder)
  body.setProperty('--surface-0', p.surface0)
  body.setProperty('--surface-1', p.surface1)
  body.setProperty('--surface-2', p.surface2)
  body.setProperty('--compresso-surface-raised', p.surfaceRaised)
  body.setProperty('--compresso-sidebar-bg', p.sidebarBg)
  body.setProperty('--compresso-header-bg', p.headerBg)
  body.setProperty('--compresso-header-gradient-end', p.headerGradientEnd)

  // Backward compat: keep --q-card-head for existing components
  body.setProperty('--q-card-head', p.surfaceRaised)

  // Chart colors
  p.chart.forEach((color: string, i: number) => {
    body.setProperty(`--compresso-chart-${i + 1}`, color)
  })

  // Body attribute for CSS selectors
  document.body.setAttribute('data-palette', paletteConfig ? palette : 'forest')
}

/**
 * Read all chart colors from CSS custom properties.
 * @returns {string[]} Array of hex color strings
 */
export function getChartColors(): string[] {
  const style = getComputedStyle(document.body)
  return Array.from({ length: 10 }, (_, i) => style.getPropertyValue(`--compresso-chart-${i + 1}`).trim() || '#808080')
}

/**
 * Read a single chart color by 1-based index.
 * @param {number} index - 1-based chart color index
 * @returns {string} Hex color string
 */
export function getChartColor(index: number): string {
  return getComputedStyle(document.body).getPropertyValue(`--compresso-chart-${index}`).trim() || '#808080'
}

/**
 * Get available palette names.
 * @returns {string[]}
 */
export function getPaletteNames(): PaletteName[] {
  return Object.keys(PALETTES) as PaletteName[]
}

/**
 * Get the primary and secondary colors for a palette (for swatch display).
 * @param {string} paletteName
 * @returns {{ light: { primary: string, secondary: string }, dark: { primary: string, secondary: string } }}
 */
export function getPalettePreview(paletteName: string) {
  if (!(paletteName in PALETTES)) return null
  const p = PALETTES[paletteName as PaletteName]
  return {
    light: { primary: p.light.primary, secondary: p.light.secondary },
    dark: { primary: p.dark.primary, secondary: p.dark.secondary },
  }
}

export { PALETTES }
