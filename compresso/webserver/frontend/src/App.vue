<template>
  <router-view/>
</template>
<script>
import { defineComponent, onBeforeUnmount } from 'vue';
import { LocalStorage, useQuasar } from "quasar";
import { applyTheme } from "src/js/compressoTheme";

export default defineComponent({
  name: 'App',
  setup() {
    const $q = useQuasar();

    // Detect system preference if no stored theme
    let configuredTheme = LocalStorage.getItem('theme');
    if (!configuredTheme) {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      configuredTheme = prefersDark ? 'dark' : 'light';
      LocalStorage.set('theme', configuredTheme);
    }

    const configuredPalette = LocalStorage.getItem('palette') || 'forest';

    const darkMode = configuredTheme === 'dark';
    applyTheme(configuredTheme, configuredPalette);
    $q.dark.set(darkMode);

    // Listen for runtime OS theme preference changes
    const mql = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    const onThemeChange = (e) => {
      // Only auto-switch if user hasn't explicitly stored a preference
      if (LocalStorage.getItem('theme')) return;
      const newTheme = e.matches ? 'dark' : 'light';
      const palette = LocalStorage.getItem('palette') || 'forest';
      applyTheme(newTheme, palette);
      $q.dark.set(e.matches);
    };
    if (mql) {
      mql.addEventListener('change', onThemeChange);
    }

    onBeforeUnmount(() => {
      if (mql) {
        mql.removeEventListener('change', onThemeChange);
      }
    });
  }
})
</script>
