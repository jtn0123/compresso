<template>
  <router-view/>
</template>
<script>
import { defineComponent } from 'vue';
import { LocalStorage, setCssVar, useQuasar } from "quasar";
import { setTheme } from "src/js/compressoGlobals";

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

    const darkMode = configuredTheme === 'dark';
    setTheme(configuredTheme);
    $q.dark.set(darkMode);
  }
})
</script>
