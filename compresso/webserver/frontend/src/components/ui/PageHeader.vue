<template>
  <div class="row items-center q-mb-lg page-header">
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
  border-bottom: 2px solid var(--q-primary);
  padding-bottom: 12px;
}

.page-header-title {
  font-size: 1.35rem;
  font-weight: 700;
  line-height: 1.3;
}

.page-header-subtitle {
  font-size: 0.8rem;
  color: var(--compresso-grey-6);
  margin-top: 2px;
}
</style>
