<template>
  <div class="flow-summary-bar q-mb-md">
    <div class="text-subtitle2 q-mb-xs">{{ $t('flow.flowSummary') }}</div>
    <div class="row items-center q-gutter-xs flex-wrap">
      <q-chip dense color="primary" text-color="white" icon="search" size="sm"> Scan </q-chip>
      <q-icon name="arrow_forward" size="16px" color="grey-6" />

      <q-chip
        dense
        :color="hasCodecFilter ? 'secondary' : 'grey-5'"
        :text-color="hasCodecFilter ? 'white' : 'grey-8'"
        icon="filter_alt"
        size="sm"
      >
        {{ $t('flow.codecFilter') }}
        <q-tooltip v-if="hasCodecFilter">
          <div v-if="targetCodecs.length">Target: {{ targetCodecs.join(', ') }}</div>
          <div v-if="skipCodecs.length">Skip: {{ skipCodecs.join(', ') }}</div>
        </q-tooltip>
      </q-chip>
      <q-icon name="arrow_forward" size="16px" color="grey-6" />

      <q-chip dense color="primary" text-color="white" icon="extension" size="sm"> Plugins </q-chip>
      <q-icon name="arrow_forward" size="16px" color="grey-6" />

      <q-chip dense color="primary" text-color="white" icon="engineering" size="sm"> Worker </q-chip>
      <q-icon name="arrow_forward" size="16px" color="grey-6" />

      <q-chip
        dense
        :color="sizeGuardrailEnabled ? 'warning' : 'grey-5'"
        :text-color="sizeGuardrailEnabled ? 'dark' : 'grey-8'"
        icon="shield"
        size="sm"
      >
        {{ $t('flow.sizeGuardrails') }}
        <q-tooltip v-if="sizeGuardrailEnabled"> {{ sizeGuardrailMinPct }}% — {{ sizeGuardrailMaxPct }}% </q-tooltip>
      </q-chip>
      <q-icon name="arrow_forward" size="16px" color="grey-6" />

      <q-chip dense :color="policyColor" text-color="white" :icon="policyIcon" size="sm">
        {{ policyLabel }}
      </q-chip>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  targetCodecs: { type: Array, default: () => [] },
  skipCodecs: { type: Array, default: () => [] },
  sizeGuardrailEnabled: { type: Boolean, default: false },
  sizeGuardrailMinPct: { type: Number, default: 20 },
  sizeGuardrailMaxPct: { type: Number, default: 80 },
  replacementPolicy: { type: String, default: '' },
  globalApprovalRequired: { type: Boolean, default: false },
})

const { t } = useI18n()

const hasCodecFilter = computed(() => props.targetCodecs.length > 0 || props.skipCodecs.length > 0)

const effectivePolicy = computed(() => {
  if (props.replacementPolicy) return props.replacementPolicy
  return props.globalApprovalRequired ? 'approval_required' : 'replace'
})

const policyLabel = computed(() => {
  const map = {
    replace: t('flow.policyReplace'),
    approval_required: t('flow.policyApproval'),
    keep_both: t('flow.policyKeepBoth'),
  }
  return map[effectivePolicy.value] || t('flow.policyReplace')
})

const policyColor = computed(() => {
  const map = {
    replace: 'positive',
    approval_required: 'info',
    keep_both: 'accent',
  }
  return map[effectivePolicy.value] || 'positive'
})

const policyIcon = computed(() => {
  const map = {
    replace: 'swap_horiz',
    approval_required: 'gavel',
    keep_both: 'file_copy',
  }
  return map[effectivePolicy.value] || 'swap_horiz'
})
</script>

<style scoped>
.flow-summary-bar {
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.02);
}
</style>
