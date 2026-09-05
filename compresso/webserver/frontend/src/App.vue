<template>
  <router-view />
</template>
<script lang="ts">
import { defineComponent, onBeforeUnmount } from 'vue'
import { LocalStorage, useQuasar } from 'quasar'
import { applyTheme, isPaletteName, isThemeMode } from 'src/js/compressoTheme'
import type { PaletteName, ThemeMode } from 'src/js/compressoTheme'

export default defineComponent({
  name: 'App',
  setup() {
    const $q = useQuasar()

    // Detect system preference if no stored theme
    const storedTheme = LocalStorage.getItem('theme')
    let configuredTheme: ThemeMode = isThemeMode(storedTheme) ? storedTheme : 'light'
    if (!isThemeMode(storedTheme)) {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      configuredTheme = prefersDark ? 'dark' : 'light'
    }

    const storedPalette = LocalStorage.getItem('palette')
    const configuredPalette: PaletteName = isPaletteName(storedPalette) ? storedPalette : 'forest'

    const darkMode = configuredTheme === 'dark'
    applyTheme(configuredTheme, configuredPalette)
    $q.dark.set(darkMode)

    // Listen for runtime OS theme preference changes
    const mql = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)')
    const onThemeChange = (e: MediaQueryListEvent): void => {
      // Only auto-switch if user hasn't explicitly chosen via ThemeSwitch
      if (LocalStorage.getItem('theme_explicit')) return
      const newTheme = e.matches ? 'dark' : 'light'
      const storedPalette = LocalStorage.getItem('palette')
      const palette: PaletteName = isPaletteName(storedPalette) ? storedPalette : 'forest'
      applyTheme(newTheme, palette)
      $q.dark.set(e.matches)
    }
    if (mql) {
      mql.addEventListener('change', onThemeChange)
    }

    onBeforeUnmount(() => {
      if (mql) {
        mql.removeEventListener('change', onThemeChange)
      }
    })
  },
})
</script>
