<template>
  <div :class="['admonition', `admonition-${type}`]">
    <div class="admonition-heading">
      <h5>
        <div class="admonition-icon">
          <q-icon :name="iconName" />
        </div>
        {{ displayTitle }}
      </h5>
    </div>
    <div class="admonition-content">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

type AdmonitionType = 'note' | 'tip' | 'warning' | 'caution' | 'important'

const props = withDefaults(defineProps<{ type?: AdmonitionType; title?: string | null }>(), {
  type: 'note',
  title: null,
})

const { t } = useI18n()

const displayTitle = computed(() => {
  if (props.title) return props.title
  return t(`components.admonitions.${props.type}`)
})

const iconName = computed(() => {
  switch (props.type) {
    case 'tip':
      return 'lightbulb'
    case 'warning':
      return 'warning'
    case 'caution':
      return 'error'
    case 'important':
      return 'campaign'
    default:
      return 'info'
  }
})
</script>
