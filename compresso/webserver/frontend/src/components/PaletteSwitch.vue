<template>
  <q-btn flat round dense icon="palette" color="grey-5">
    <q-tooltip>Color palette</q-tooltip>
    <q-menu anchor="bottom right" self="top right" :offset="[0, 4]">
      <q-list dense style="min-width: 140px">
        <q-item-label header class="text-caption text-weight-medium q-pb-xs">Palette</q-item-label>
        <q-item
          v-for="name in paletteNames"
          :key="name"
          clickable
          v-close-popup
          @click="selectPalette(name)"
          :active="name === currentPalette"
          active-class="palette-active"
          dense
        >
          <q-item-section side>
            <div class="row no-wrap q-gutter-xs">
              <div
                class="palette-swatch"
                :style="{ background: getSwatchColor(name, 'primary') }"
              />
              <div
                class="palette-swatch"
                :style="{ background: getSwatchColor(name, 'secondary') }"
              />
            </div>
          </q-item-section>
          <q-item-section>
            <q-item-label class="text-capitalize text-caption">{{ name }}</q-item-label>
          </q-item-section>
          <q-item-section v-if="name === currentPalette" side>
            <q-icon name="check" size="14px" color="primary" />
          </q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup>
import { ref } from 'vue'
import { LocalStorage, useQuasar } from 'quasar'
import { applyTheme, getPaletteNames, getPalettePreview } from 'src/js/compressoTheme'

const $q = useQuasar()
const paletteNames = getPaletteNames()
const currentPalette = ref(LocalStorage.getItem('palette') || 'forest')

function getSwatchColor(paletteName, key) {
  const preview = getPalettePreview(paletteName)
  if (!preview) return '#888'
  const mode = $q.dark.isActive ? 'dark' : 'light'
  return preview[mode][key]
}

function selectPalette(name) {
  currentPalette.value = name
  LocalStorage.set('palette', name)
  const mode = $q.dark.isActive ? 'dark' : 'light'
  applyTheme(mode, name)
}
</script>

<style scoped>
.palette-swatch {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid rgba(128, 128, 128, 0.2);
}

.palette-active {
  background: color-mix(in srgb, var(--q-primary) 8%, transparent);
}
</style>
