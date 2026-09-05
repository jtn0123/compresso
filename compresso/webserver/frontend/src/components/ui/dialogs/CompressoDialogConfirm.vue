<template>
  <q-dialog ref="dialogRef" :persistent="persistent" @hide="onDialogHide">
    <q-card class="confirm-dialog-card" flat bordered>
      <q-card-section class="bg-card-head text-primary">
        {{ resolvedTitle }}
      </q-card-section>

      <q-card-section class="q-pa-md">
        <slot>
          <div>{{ resolvedMessage }}</div>
        </slot>
      </q-card-section>

      <q-card-actions align="right" class="q-pa-md">
        <q-btn outline :color="cancelColor" :label="resolvedCancelLabel" @click="onCancel" />
        <q-btn outline :color="okColor" :label="resolvedOkLabel" @click="onConfirm" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DialogController } from 'src/types/ui'

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  message: {
    type: String,
    default: '',
  },
  okLabel: {
    type: String,
    default: '',
  },
  cancelLabel: {
    type: String,
    default: '',
  },
  okColor: {
    type: String,
    default: 'secondary',
  },
  cancelColor: {
    type: String,
    default: 'secondary',
  },
  persistent: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['confirm', 'cancel', 'hide'])

const { t } = useI18n()
const dialogRef = ref<DialogController | null>(null)

const resolvedTitle = computed(() => props.title || t('headers.confirm'))

const resolvedMessage = computed(() => props.message || t('components.settings.library.confirmRemove'))

const resolvedOkLabel = computed(() => props.okLabel || t('navigation.yes'))

const resolvedCancelLabel = computed(() => props.cancelLabel || t('navigation.cancel'))

const show = () => {
  dialogRef.value?.show()
}

const hide = () => {
  dialogRef.value?.hide()
}

const onConfirm = () => {
  emit('confirm')
  hide()
}

const onCancel = () => {
  emit('cancel')
  hide()
}

const onDialogHide = () => {
  emit('hide')
}

defineExpose({
  show,
  hide,
})
</script>

<style scoped>
.confirm-dialog-card {
  width: 480px;
  max-width: 95vw;
}
</style>
