<template>
  <div class="row items-center q-mb-md page-header">
    <div class="col">
      <div class="page-header-title">{{ title }}</div>
      <div v-if="subtitle" class="page-header-subtitle">{{ subtitle }}</div>
    </div>
    <div v-if="$slots.actions" class="col-auto q-gutter-sm">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
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

<style scoped>
.page-header {
  border-bottom: 1px solid color-mix(in srgb, var(--q-primary), transparent 70%);
  padding-bottom: 10px;
}

.page-header-title {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.3;
}

.page-header-subtitle {
  font-size: 0.78rem;
  color: var(--compresso-grey-6);
  margin-top: 2px;
}
</style>
