import { useQuasar } from 'quasar'

export function useWorkerGauges() {
  const $q = useQuasar()

  const clampPercent = (value) => {
    if (!Number.isFinite(value)) {
      return 0
    }
    return Math.max(0, Math.min(100, value))
  }

  const formatPercent = (value) => {
    return Number(parseFloat(value.toFixed(2)))
  }

  const gradientColor = (percent) => {
    const clamped = clampPercent(percent)
    const isDark = $q.dark.isActive
    const secondary = isDark
      ? { r: 64, g: 200, b: 255 }
      : { r: 0, g: 120, b: 180 }
    const red = isDark
      ? { r: 255, g: 90, b: 90 }
      : { r: 180, g: 20, b: 20 }
    const ratio = clamped / 100
    const r = Math.round(secondary.r + (red.r - secondary.r) * ratio)
    const g = Math.round(secondary.g + (red.g - secondary.g) * ratio)
    const b = Math.round(secondary.b + (red.b - secondary.b) * ratio)
    return `rgb(${r}, ${g}, ${b})`
  }

  // Generate a deterministic hex colour from a string name (for worker group chips)
  // Credit: https://stackoverflow.com/questions/3426404/create-a-hexadecimal-colour-based-on-a-string-with-javascript
  const generateGroupColour = (name) => {
    let hash = 0
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash)
    }
    let colour = '#'
    for (let i = 0; i < 3; i++) {
      const value = (hash >> (i * 8)) & 0xFF
      colour += ('00' + value.toString(16)).substr(-2)
    }
    return colour
  }

  return {
    clampPercent,
    formatPercent,
    gradientColor,
    generateGroupColour
  }
}
