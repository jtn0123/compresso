<template>
  <q-btn
    flat
    dense
    round
    :size="size"
    :color="color"
    :icon="icon"
    :disable="disable"
    :aria-label="accessibleName || undefined"
    @click="$emit('click', $event)"
  >
    <q-tooltip v-if="tooltip" class="bg-white text-primary">
      {{ tooltip }}
    </q-tooltip>
    <slot />
  </q-btn>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps({
  icon: {
    type: String,
    required: true,
  },
  color: {
    type: String,
    default: 'secondary',
  },
  size: {
    type: String,
    default: '12px',
  },
  tooltip: {
    type: String,
    default: '',
  },
  disable: {
    type: Boolean,
    default: false,
  },
  // Icon-only buttons have no text for a screen reader to announce, and a
  // tooltip is not an accessible name. Callers that already pass `tooltip` get
  // one for free; anything without either is a bug caught by the axe sweep.
  ariaLabel: {
    type: String,
    default: '',
  },
})

const accessibleName = computed(() => props.ariaLabel || props.tooltip)

defineEmits(['click'])
</script>
