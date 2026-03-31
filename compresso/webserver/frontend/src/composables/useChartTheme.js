/**
 * Composable for palette-aware Chart.js colors.
 * Use this instead of hardcoding color arrays in chart components.
 */
import { getChartColors, getChartColor } from 'src/js/compressoTheme'

export function useChartTheme() {
  /**
   * Get a transparent background variant of a chart color.
   * @param {number} index - 1-based chart color index
   * @param {number} [alpha=0.1] - Opacity (0-1)
   * @returns {string} Hex color with alpha suffix
   */
  function chartBgColor(index, alpha = 0.1) {
    const hex = getChartColor(index)
    const alphaHex = Math.round(alpha * 255).toString(16).padStart(2, '0')
    return hex + alphaHex
  }

  return {
    getChartColors,
    getChartColor,
    chartBgColor,
  }
}
