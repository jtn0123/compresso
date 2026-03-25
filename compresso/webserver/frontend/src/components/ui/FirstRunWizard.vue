<template>
  <q-dialog v-model="dialogVisible" persistent no-backdrop-dismiss>
    <q-card style="min-width: 560px; max-width: 680px">
      <q-card-section>
        <div class="text-h5">{{ $t('onboarding.welcomeTitle') }}</div>
        <div class="text-caption text-grey">{{ $t('onboarding.welcomeSubtitle') }}</div>
      </q-card-section>

      <q-stepper v-model="step" animated flat>
        <!-- Step 1: Library Path -->
        <q-step :name="1" :title="$t('onboarding.stepLibraryTitle')" icon="folder" :done="step > 1">
          <div class="q-mb-md">{{ $t('onboarding.stepLibraryPrompt') }}</div>
          <q-input
            v-model="libraryPath"
            :label="$t('onboarding.stepLibraryLabel')"
            outlined
          />
          <div class="text-caption text-grey q-mt-xs">
            {{ $t('onboarding.stepLibraryHint') }}
          </div>
        </q-step>

        <!-- Step 2: Approval Workflow -->
        <q-step :name="2" :title="$t('onboarding.stepApprovalTitle')" icon="verified" :done="step > 2">
          <div class="q-mb-md">{{ $t('onboarding.stepApprovalPrompt') }}</div>
          <q-option-group
            v-model="approvalMode"
            :options="approvalOptions"
            type="radio"
          />
          <div class="text-caption text-grey q-mt-sm">
            {{ $t('onboarding.stepApprovalHint') }}
          </div>
        </q-step>

        <!-- Step 3: Workers -->
        <q-step :name="3" :title="$t('onboarding.stepWorkersTitle')" icon="memory" :done="step > 3">
          <div class="q-mb-md">{{ $t('onboarding.stepWorkersPrompt') }}</div>
          <q-slider
            v-model="workerCount"
            :min="1"
            :max="4"
            :step="1"
            label
            snap
            markers
          />
          <div class="text-caption text-grey q-mt-xs">
            {{ $t('onboarding.stepWorkersHint', { count: workerCount }) }}
          </div>
        </q-step>
      </q-stepper>

      <q-card-actions align="right" class="q-pa-md">
        <q-btn
          v-if="step > 1"
          flat
          :label="$t('onboarding.back')"
          @click="step--"
        />
        <q-space/>
        <q-btn
          v-if="step < 3"
          color="primary"
          :label="$t('onboarding.next')"
          @click="step++"
          :disable="step === 1 && !libraryPath.trim()"
        />
        <q-btn
          v-else
          color="primary"
          :label="$t('onboarding.finishSetup')"
          :loading="saving"
          @click="completeOnboarding"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'

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
    const step = ref(1)
    const saving = ref(false)

    // Form state
    const libraryPath = ref('')
    const approvalMode = ref(false)
    const workerCount = ref(1)

    watch(() => props.modelValue, (val) => {
      dialogVisible.value = val
    })

    const approvalOptions = computed(() => [
      { label: t('onboarding.approvalEnabled'), value: true },
      { label: t('onboarding.approvalDisabled'), value: false },
    ])

    // Pre-fill defaults from current settings
    axios.get(getCompressoApiUrl('v2', 'settings/read')).then((res) => {
      const settings = res.data?.settings || {}
      if (settings.library_path) libraryPath.value = settings.library_path
      if (settings.approval_required !== undefined) approvalMode.value = !!settings.approval_required
      if (settings.number_of_workers) workerCount.value = Math.min(4, Math.max(1, parseInt(settings.number_of_workers) || 1))
    }).catch(() => {
      // Ignore — wizard uses reasonable defaults
    })

    async function completeOnboarding() {
      saving.value = true
      try {
        await axios.post(getCompressoApiUrl('v2', 'settings/write'), {
          settings: {
            library_path: libraryPath.value,
            approval_required: approvalMode.value,
            number_of_workers: workerCount.value,
            onboarding_completed: true,
          }
        })
        dialogVisible.value = false
        emit('update:modelValue', false)
      } catch (e) {
        console.error('Failed to save onboarding settings:', e)
      } finally {
        saving.value = false
      }
    }

    return {
      dialogVisible,
      step,
      saving,
      libraryPath,
      approvalMode,
      workerCount,
      approvalOptions,
      completeOnboarding,
    }
  }
}
</script>
