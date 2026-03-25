<template>
  <q-dialog v-model="dialogVisible" @hide="$emit('update:modelValue', false)">
    <q-card style="min-width: 420px; max-width: 520px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ $t('keyboardShortcuts.title') }}</div>
        <q-space/>
        <q-btn icon="close" flat round dense v-close-popup/>
      </q-card-section>

      <q-card-section>
        <!-- Navigation shortcuts -->
        <div class="text-subtitle2 text-grey q-mb-sm">{{ $t('keyboardShortcuts.navigation') }}</div>
        <q-markup-table flat dense separator="none" class="q-mb-md">
          <tbody>
            <tr v-for="shortcut in navigationShortcuts" :key="shortcut.keys">
              <td style="width: 120px">
                <span v-for="(key, idx) in shortcut.keys.split(' ')" :key="idx">
                  <kbd class="shortcut-key">{{ key }}</kbd>
                  <span v-if="idx < shortcut.keys.split(' ').length - 1" class="text-grey-6 q-mx-xs">then</span>
                </span>
              </td>
              <td class="text-grey-8">{{ shortcut.label }}</td>
            </tr>
          </tbody>
        </q-markup-table>

        <!-- Action shortcuts -->
        <div class="text-subtitle2 text-grey q-mb-sm">{{ $t('keyboardShortcuts.actions') }}</div>
        <q-markup-table flat dense separator="none">
          <tbody>
            <tr v-for="shortcut in actionShortcuts" :key="shortcut.keys">
              <td style="width: 120px">
                <kbd class="shortcut-key">{{ shortcut.keys }}</kbd>
              </td>
              <td class="text-grey-8">{{ shortcut.label }}</td>
            </tr>
            <tr>
              <td style="width: 120px">
                <kbd class="shortcut-key">Esc</kbd>
              </td>
              <td class="text-grey-8">{{ $t('navigation.close') }}</td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <div class="text-caption text-grey text-center">
          {{ $t('keyboardShortcuts.pressEscToClose') }}
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script>
import { computed, watch, ref } from 'vue'
import { useI18n } from 'vue-i18n'

export default {
  props: {
    modelValue: {
      type: Boolean,
      default: false
    }
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const { t } = useI18n()
    const dialogVisible = ref(props.modelValue)

    watch(() => props.modelValue, (val) => {
      dialogVisible.value = val
    })

    watch(dialogVisible, (val) => {
      if (!val) {
        emit('update:modelValue', false)
      }
    })

    const navigationShortcuts = computed(() => [
      { keys: 'g d', label: t('keyboardShortcuts.goToDashboard') },
      { keys: 'g c', label: t('keyboardShortcuts.goToCompression') },
      { keys: 'g a', label: t('keyboardShortcuts.goToApproval') },
      { keys: 'g h', label: t('keyboardShortcuts.goToHealth') },
      { keys: 'g p', label: t('keyboardShortcuts.goToPreview') },
      { keys: 'g s', label: t('keyboardShortcuts.goToSettingsLibrary') },
      { keys: 'g w', label: t('keyboardShortcuts.goToSettingsWorkers') },
    ])

    const actionShortcuts = computed(() => [
      { keys: '?', label: t('keyboardShortcuts.showHelp') },
    ])

    return {
      dialogVisible,
      navigationShortcuts,
      actionShortcuts,
    }
  }
}
</script>

<style scoped>
.shortcut-key {
  display: inline-block;
  padding: 2px 8px;
  font-family: monospace;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--q-dark, #1d1d1d);
  background: rgba(128, 128, 128, 0.12);
  border: 1px solid rgba(128, 128, 128, 0.25);
  border-radius: 4px;
  min-width: 24px;
  text-align: center;
}
</style>
