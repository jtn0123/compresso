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
      primarySoft: '#e6f2ec',
      primaryBorder: '#b3d4c4',
      surface0: '#f5f6f7',
      surface1: '#ffffff',
      surface2: '#f8f9fa',
      surfaceRaised: '#f0f3f1',
      headerBg: '#13291f',
      headerGradientEnd: '#1a3d2d',
      chart: [
        '#1a6b4a', '#d49a1e', '#7c5cbf', '#d43545', '#2e9e5a',
        '#3a8fd4', '#e67e22', '#1abc9c', '#34495e', '#95a5a6',
      ],
    },
    dark: {
      primary: '#2da87a',
      secondary: '#e8a525',
      accent: '#9a80d4',
      warning: '#e8a525',
      primarySoft: '#1a2e26',
      primaryBorder: '#264a3a',
      surface0: '#111114',
      surface1: '#1a1a1e',
      surface2: '#222226',
      surfaceRaised: '#252528',
      headerBg: '#0f1f18',
      headerGradientEnd: '#152e22',
      chart: [
        '#2da87a', '#e8a525', '#9a80d4', '#e06060', '#3ebe70',
        '#5aafee', '#f0a050', '#40d8b0', '#8898a8', '#b0b8c0',
      ],
    },
  },
  ember: {
    light: {
      primary: '#c05621',
      secondary: '#4a6670',
      accent: '#8b6f47',
      warning: '#c05621',
      primarySoft: '#fdf0e8',
      primaryBorder: '#f0c9a8',
      surface0: '#f6f5f4',
      surface1: '#ffffff',
      surface2: '#faf8f7',
      surfaceRaised: '#f3f1ef',
      headerBg: '#2c2017',
      headerGradientEnd: '#3d2e22',
      chart: [
        '#c05621', '#4a6670', '#8b6f47', '#d43545', '#2e9e5a',
        '#3a8fd4', '#b8512e', '#1abc9c', '#5d4e37', '#95a5a6',
      ],
    },
    dark: {
      primary: '#e07030',
      secondary: '#7a9aa8',
      accent: '#b8965e',
      warning: '#e07030',
      primarySoft: '#2c2018',
      primaryBorder: '#4a3425',
      surface0: '#131210',
      surface1: '#1c1a18',
      surface2: '#262320',
      surfaceRaised: '#2a2720',
      headerBg: '#1a150f',
      headerGradientEnd: '#2a2018',
      chart: [
        '#e07030', '#7a9aa8', '#b8965e', '#e06060', '#3ebe70',
        '#5aafee', '#f0a050', '#40d8b0', '#8898a8', '#b0b8c0',
      ],
    },
  },
}

/**
 * Apply a theme (mode + palette) to the application.
 * Sets all Quasar and custom CSS variables.
 *
 * @param {'light'|'dark'} mode
 * @param {'forest'|'ember'} palette
 */
export function applyTheme(mode, palette) {
  const p = PALETTES[palette]?.[mode] || PALETTES.forest.light

  // Quasar built-in CSS vars
  setCssVar('primary', p.primary)
  setCssVar('secondary', p.secondary)
  setCssVar('accent', p.accent)
  setCssVar('warning', p.warning)

  // Extended Compresso CSS vars
  const body = document.body.style
  body.setProperty('--compresso-primary-soft', p.primarySoft)
  body.setProperty('--compresso-primary-border', p.primaryBorder)
  body.setProperty('--surface-0', p.surface0)
  body.setProperty('--surface-1', p.surface1)
  body.setProperty('--surface-2', p.surface2)
  body.setProperty('--compresso-surface-raised', p.surfaceRaised)
  body.setProperty('--compresso-header-bg', p.headerBg)
  body.setProperty('--compresso-header-gradient-end', p.headerGradientEnd)

  // Backward compat: keep --q-card-head for existing components
  body.setProperty('--q-card-head', p.surfaceRaised)

  // Chart colors
  p.chart.forEach((color, i) => {
    body.setProperty(`--compresso-chart-${i + 1}`, color)
  })

  // Body attribute for CSS selectors
  document.body.setAttribute('data-palette', palette)
}

/**
 * Read all chart colors from CSS custom properties.
 * @returns {string[]} Array of hex color strings
 */
export function getChartColors() {
  const style = getComputedStyle(document.body)
  return Array.from({ length: 10 }, (_, i) =>
    style.getPropertyValue(`--compresso-chart-${i + 1}`).trim()
  )
}

/**
 * Read a single chart color by 1-based index.
 * @param {number} index - 1-based chart color index
 * @returns {string} Hex color string
 */
export function getChartColor(index) {
  return getComputedStyle(document.body)
    .getPropertyValue(`--compresso-chart-${index}`)
    .trim()
}

/**
 * Get available palette names.
 * @returns {string[]}
 */
export function getPaletteNames() {
  return Object.keys(PALETTES)
}

/**
 * Get the primary and secondary colors for a palette (for swatch display).
 * @param {string} paletteName
 * @returns {{ light: { primary: string, secondary: string }, dark: { primary: string, secondary: string } }}
 */
export function getPalettePreview(paletteName) {
  const p = PALETTES[paletteName]
  if (!p) return null
  return {
    light: { primary: p.light.primary, secondary: p.light.secondary },
    dark: { primary: p.dark.primary, secondary: p.dark.secondary },
  }
}

export { PALETTES }
