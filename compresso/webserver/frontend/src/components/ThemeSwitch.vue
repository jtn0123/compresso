<template>
  <q-btn
    flat
    round
    dense
    :icon="compressoDarkMode ? 'dark_mode' : 'light_mode'"
    :color="compressoDarkMode ? 'amber-4' : 'grey-7'"
    @click="toggleMode"
  >
    <q-tooltip>{{ compressoDarkMode ? 'Light mode' : 'Dark mode' }}</q-tooltip>
  </q-btn>
</template>

<script>
import { LocalStorage, useQuasar } from 'quasar'
import { ref } from "vue";
import { applyTheme } from "src/js/compressoTheme";

export default {
  setup() {
    const $q = useQuasar();
    const compressoDarkMode = ref($q.dark.isActive);

    function toggleMode() {
      compressoDarkMode.value = !compressoDarkMode.value;
      const themeName = compressoDarkMode.value ? 'dark' : 'light';
      const palette = LocalStorage.getItem('palette') || 'forest';
      LocalStorage.set('theme', themeName);
      $q.dark.set(compressoDarkMode.value);
      applyTheme(themeName, palette);
    }

    return {
      compressoDarkMode,
      toggleMode,
    }
  },
}
</script>
