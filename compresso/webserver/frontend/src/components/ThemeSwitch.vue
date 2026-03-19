<template>
  <q-toggle
    :icon="compressoDarkMode? 'dark_mode' : 'light_mode'"
    color="secondary"
    v-model="compressoDarkMode"/>
</template>

<script>
import { LocalStorage, useQuasar } from 'quasar'
import { ref } from "vue";
import { setTheme } from "src/js/compressoGlobals";

export default {
  setup() {
    const $q = useQuasar();
    const compressoDarkMode = ref($q.dark.isActive);
    return {
      compressoDarkMode,
    }
  },
  watch: {
    compressoDarkMode(mode) {
      if (mode) {
        LocalStorage.set('theme', 'dark');
        this.$q.dark.set(true);
        setTheme('dark')
      } else {
        LocalStorage.set('theme', 'light');
        this.$q.dark.set(false);
        setTheme('light')
      }
    }
  }
}
</script>
