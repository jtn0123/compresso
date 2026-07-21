<template>
  <!-- Page title + subtitle now live in the app top bar; this renders page-level actions only -->
  <div v-if="$slots.actions" class="row items-center justify-end q-gutter-sm q-mb-md page-header">
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
})
</script>
