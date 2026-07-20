<template>
  <q-page padding>
    <div class="q-pa-md comparison-page">
      <PageHeader :title="t('pages.sampleComparison.title')" />

      <q-card v-if="!batch" flat bordered class="setup-card q-mb-lg">
        <q-card-section class="setup-heading">
          <div>
            <div class="text-overline text-secondary">{{ t('pages.sampleComparison.setupKicker') }}</div>
            <div class="text-h6">{{ t('pages.sampleComparison.setupTitle') }}</div>
            <div class="text-body2 text-grey-7 q-mt-xs">{{ t('pages.sampleComparison.setupDescription') }}</div>
          </div>
          <q-badge :color="selectionValid ? 'positive' : 'warning'" class="selection-badge">
            {{ t('pages.sampleComparison.selectedCount', { count: selectedProfileKeys.length }) }}
          </q-badge>
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-input
            v-model="sourcePath"
            outlined
            readonly
            color="primary"
            :label="t('pages.sampleComparison.sourceFile')"
            :placeholder="t('pages.sampleComparison.sourcePlaceholder')"
            class="source-input q-mb-md"
            @click="openPicker"
          >
            <template #prepend><q-icon name="movie" /></template>
            <template #append>
              <q-btn
                flat
                round
                icon="folder_open"
                :aria-label="t('pages.sampleComparison.browse')"
                @click.stop="openPicker"
              >
                <q-tooltip>{{ t('pages.sampleComparison.browse') }}</q-tooltip>
              </q-btn>
            </template>
          </q-input>

          <div class="row q-col-gutter-md q-mb-lg">
            <div class="col-12 col-md-4">
              <q-select
                v-model="libraryId"
                :options="libraryOptions"
                emit-value
                map-options
                outlined
                color="primary"
                :label="t('pages.sampleComparison.library')"
                @update:model-value="onLibraryChanged"
              />
            </div>
            <div class="col-6 col-md-4">
              <q-input
                v-model.number="startTime"
                type="number"
                min="0"
                outlined
                color="primary"
                :label="t('pages.sampleComparison.startTime')"
                :suffix="t('pages.sampleComparison.secondsShort')"
              />
            </div>
            <div class="col-6 col-md-4">
              <q-input
                v-model.number="sampleDuration"
                type="number"
                min="1"
                max="30"
                outlined
                color="primary"
                :label="t('pages.sampleComparison.duration')"
                :suffix="t('pages.sampleComparison.secondsShort')"
              />
            </div>
          </div>

          <div class="profile-heading q-mb-sm">
            <div>
              <div class="text-subtitle1 text-weight-medium">{{ t('pages.sampleComparison.chooseProfiles') }}</div>
              <div class="text-caption text-grey-7">{{ t('pages.sampleComparison.profileLimit') }}</div>
            </div>
          </div>

          <div v-if="profilesLoading" class="row justify-center q-pa-lg">
            <q-spinner color="secondary" size="36px" />
          </div>
          <div v-else class="profile-grid">
            <label
              v-for="profile in profiles"
              :key="profile.key"
              class="profile-option"
              :class="{
                'profile-option--selected': selectedProfileKeys.includes(profile.key),
                'profile-option--disabled': !profile.available,
              }"
            >
              <q-checkbox
                :model-value="selectedProfileKeys.includes(profile.key)"
                :disable="
                  !profile.available || (!selectedProfileKeys.includes(profile.key) && selectedProfileKeys.length >= 4)
                "
                color="secondary"
                @update:model-value="toggleProfile(profile.key)"
              />
              <span class="profile-copy">
                <strong>{{ profile.label }}</strong>
                <span>{{ profile.description }}</span>
                <small>{{ profile.encoder }} · {{ profile.codec.toUpperCase() }}</small>
              </span>
              <q-badge v-if="profile.hardware" outline color="secondary">
                {{ t('pages.sampleComparison.hardware') }}
              </q-badge>
              <q-badge v-if="!profile.available" color="grey-7">
                {{ t('pages.sampleComparison.unavailable') }}
              </q-badge>
            </label>
          </div>
        </q-card-section>

        <q-card-actions class="q-pa-md q-pt-none">
          <q-btn
            class="full-width"
            color="secondary"
            icon="science"
            :label="t('pages.sampleComparison.startBakeoff')"
            :loading="creating"
            :disable="!canCreate"
            @click="createComparison"
          />
        </q-card-actions>
      </q-card>

      <template v-else>
        <div class="batch-toolbar q-mb-md">
          <div class="batch-source">
            <span>{{ t('pages.sampleComparison.nowComparing') }}</span>
            <strong>{{ sourceName }}</strong>
          </div>
          <div class="row items-center q-gutter-sm">
            <q-badge :color="batchStatusColor">{{ batchStatusLabel }}</q-badge>
            <q-btn
              v-if="isTerminal"
              outline
              color="secondary"
              icon="refresh"
              :label="t('pages.sampleComparison.newComparison')"
              @click="resetComparison"
            />
          </div>
        </div>

        <q-linear-progress
          v-if="!isTerminal"
          :value="batchProgress / 100"
          color="secondary"
          track-color="grey-4"
          size="6px"
          class="q-mb-md"
        />

        <AdmonitionBanner v-if="batch.error" type="warning" class="q-mb-md">
          {{ batch.error }}
        </AdmonitionBanner>

        <MultiVideoCompare
          :candidates="batch.candidates"
          :selected-candidate-uuid="selectedWinnerUuid"
          :winner-enabled="batch.status === 'completed'"
          @winner-selected="selectWinner"
        />

        <q-card v-if="batch.status === 'completed'" flat bordered class="winner-handoff q-mt-md">
          <q-card-section class="row items-center q-col-gutter-md">
            <div class="col-12 col-md">
              <div class="text-overline text-secondary">{{ t('pages.sampleComparison.handoffKicker') }}</div>
              <div class="text-h6">{{ winnerLabel }}</div>
              <div class="text-body2 text-grey-7">
                {{
                  batch.full_encode_task_id
                    ? t('pages.sampleComparison.fullEncodeQueued', { id: batch.full_encode_task_id })
                    : t('pages.sampleComparison.handoffDescription')
                }}
              </div>
            </div>
            <div class="col-12 col-md-auto">
              <q-btn
                color="secondary"
                icon="playlist_add"
                :label="t('pages.sampleComparison.queueFullEncode')"
                :loading="queueingWinner"
                :disable="!selectedWinnerUuid || Boolean(batch.full_encode_task_id)"
                @click="queueWinner"
              />
            </div>
          </q-card-section>
        </q-card>
      </template>

      <SelectMediaFileDialog ref="filePickerRef" :initial-path="filePickerInitialPath" @selected="onFileSelected" />
    </div>
  </q-page>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import axios from 'axios'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { createLogger } from 'src/composables/useLogger'
import AdmonitionBanner from 'components/ui/AdmonitionBanner.vue'
import MultiVideoCompare from 'components/preview/MultiVideoCompare.vue'
import PageHeader from 'components/ui/PageHeader.vue'
import SelectMediaFileDialog from 'components/ui/pickers/SelectMediaFileDialog.vue'

const $q = useQuasar()
const { t } = useI18n()
const log = createLogger('SampleComparison')
const sourcePath = ref('')
const startTime = ref(0)
const sampleDuration = ref(10)
const libraryId = ref(1)
const libraryOptions = ref([])
const profiles = ref([])
const selectedProfileKeys = ref([])
const profilesLoading = ref(true)
const creating = ref(false)
const queueingWinner = ref(false)
const batchUuid = ref('')
const batch = ref(null)
const selectedWinnerUuid = ref('')
const filePickerRef = ref(null)
let pollTimer = null

const selectionValid = computed(() => selectedProfileKeys.value.length >= 2 && selectedProfileKeys.value.length <= 4)
const selectedLibrary = computed(() => libraryOptions.value.find((option) => option.value === libraryId.value))
const canCreate = computed(
  () =>
    Boolean(sourcePath.value) &&
    Boolean(selectedLibrary.value) &&
    selectionValid.value &&
    Number(sampleDuration.value) >= 1 &&
    Number(sampleDuration.value) <= 30 &&
    !profilesLoading.value &&
    !creating.value,
)
const isTerminal = computed(() => ['completed', 'failed'].includes(batch.value?.status))
const sourceName = computed(() => {
  const path = batch.value?.source_path || sourcePath.value
  return path.split(/[\\/]/).pop() || path
})
const filePickerInitialPath = computed(() => selectedLibrary.value?.path || '/')
const batchProgress = computed(() => {
  const candidates = batch.value?.candidates || []
  if (!candidates.length) return Number(batch.value?.progress) || 0
  return candidates.reduce((total, candidate) => total + (Number(candidate.progress) || 0), 0) / candidates.length
})
const winner = computed(() =>
  batch.value?.candidates?.find((candidate) => candidate.candidate_uuid === selectedWinnerUuid.value),
)
const winnerLabel = computed(() => winner.value?.profile_label || t('pages.sampleComparison.noWinner'))
const batchStatusLabel = computed(() => {
  const key = batch.value?.status || 'queued'
  return t(`pages.sampleComparison.status.${key}`)
})
const batchStatusColor = computed(() => {
  if (batch.value?.status === 'completed') return 'positive'
  if (batch.value?.status === 'failed') return 'negative'
  return 'secondary'
})

function chooseDefaults() {
  const preferred = ['x265_crf_22', 'svt_av1_crf_30', 'amd_amf_hevc_quality', 'x264_crf_23', 'x265_crf_26']
  const available = new Set(profiles.value.filter((profile) => profile.available).map((profile) => profile.key))
  selectedProfileKeys.value = preferred.filter((key) => available.has(key)).slice(0, 3)
}

async function loadSetupData() {
  profilesLoading.value = true
  try {
    const [profileResponse, settingsResponse] = await Promise.all([
      axios.get(getCompressoApiUrl('v2', 'comparison/profiles')),
      axios.get(getCompressoApiUrl('v2', 'settings/read')),
    ])
    profiles.value = profileResponse.data.profiles || []
    chooseDefaults()
    const libraries = settingsResponse.data?.settings?.libraries || []
    libraryOptions.value = libraries.map((library) => ({
      label: library.name || t('pages.sampleComparison.libraryFallback', { id: library.id }),
      value: library.id,
      path: library.path,
    }))
    if (libraryOptions.value.length) libraryId.value = libraryOptions.value[0].value
  } catch (error) {
    log.error('Failed to load comparison setup: ' + error)
    $q.notify({ type: 'negative', message: t('pages.sampleComparison.failedLoadSetup') })
  } finally {
    profilesLoading.value = false
  }
}

function toggleProfile(profileKey) {
  const selected = selectedProfileKeys.value.includes(profileKey)
  if (selected) {
    selectedProfileKeys.value = selectedProfileKeys.value.filter((key) => key !== profileKey)
  } else if (selectedProfileKeys.value.length < 4) {
    selectedProfileKeys.value = [...selectedProfileKeys.value, profileKey]
  }
}

function placeholderCandidates() {
  return selectedProfileKeys.value.map((profileKey) => {
    const profile = profiles.value.find((item) => item.key === profileKey)
    return {
      candidate_uuid: profileKey,
      profile_key: profileKey,
      profile_label: profile?.label || profileKey,
      encoder: profile?.encoder || '',
      codec: profile?.codec || '',
      status: 'queued',
      progress: 0,
    }
  })
}

async function createComparison() {
  if (!canCreate.value) return
  creating.value = true
  try {
    const response = await axios.post(getCompressoApiUrl('v2', 'comparison/create'), {
      source_path: sourcePath.value,
      start_time: Number(startTime.value) || 0,
      duration: Number(sampleDuration.value),
      library_id: libraryId.value,
      profile_keys: selectedProfileKeys.value,
    })
    batchUuid.value = response.data.batch_uuid
    batch.value = { status: 'queued', progress: 0, candidates: placeholderCandidates() }
    await refreshStatus()
  } catch (error) {
    log.error('Failed to create comparison: ' + error)
    $q.notify({ type: 'negative', message: t('pages.sampleComparison.failedCreate') })
  } finally {
    creating.value = false
  }
}

function schedulePoll() {
  stopPolling()
  if (!isTerminal.value) pollTimer = setTimeout(refreshStatus, 1000)
}

async function refreshStatus() {
  if (!batchUuid.value) return
  try {
    const response = await axios.post(getCompressoApiUrl('v2', 'comparison/status'), {
      batch_uuid: batchUuid.value,
    })
    batch.value = response.data
    if (response.data.winner_candidate_id && !selectedWinnerUuid.value) {
      const savedWinner = response.data.candidates.find(
        (candidate) => candidate.id === response.data.winner_candidate_id,
      )
      selectedWinnerUuid.value = savedWinner?.candidate_uuid || ''
    }
    schedulePoll()
  } catch (error) {
    log.error('Failed to refresh comparison status: ' + error)
    stopPolling()
    $q.notify({ type: 'negative', message: t('pages.sampleComparison.failedStatus') })
  }
}

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

async function selectWinner(candidateUuid) {
  const previous = selectedWinnerUuid.value
  selectedWinnerUuid.value = candidateUuid
  try {
    const response = await axios.post(getCompressoApiUrl('v2', 'comparison/winner'), {
      batch_uuid: batchUuid.value,
      candidate_uuid: candidateUuid,
      queue_full_encode: false,
    })
    batch.value = response.data
  } catch (error) {
    selectedWinnerUuid.value = previous
    log.error('Failed to save comparison winner: ' + error)
    $q.notify({ type: 'negative', message: t('pages.sampleComparison.failedWinner') })
  }
}

async function queueWinner() {
  if (!selectedWinnerUuid.value) return
  queueingWinner.value = true
  try {
    const response = await axios.post(getCompressoApiUrl('v2', 'comparison/winner'), {
      batch_uuid: batchUuid.value,
      candidate_uuid: selectedWinnerUuid.value,
      queue_full_encode: true,
    })
    batch.value = response.data
    $q.notify({ type: 'positive', message: t('pages.sampleComparison.queuedSuccess') })
  } catch (error) {
    log.error('Failed to queue comparison winner: ' + error)
    $q.notify({ type: 'negative', message: t('pages.sampleComparison.failedQueue') })
  } finally {
    queueingWinner.value = false
  }
}

async function resetComparison() {
  stopPolling()
  if (batchUuid.value && isTerminal.value) {
    try {
      await axios.post(getCompressoApiUrl('v2', 'comparison/cleanup'), { batch_uuid: batchUuid.value })
    } catch (error) {
      log.warn('Failed to clean up comparison cache: ' + error)
    }
  }
  batchUuid.value = ''
  batch.value = null
  selectedWinnerUuid.value = ''
}

function openPicker() {
  filePickerRef.value?.show()
}

function onLibraryChanged() {
  sourcePath.value = ''
}

function onFileSelected({ selectedPath }) {
  sourcePath.value = selectedPath
}

onMounted(loadSetupData)
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.comparison-page {
  max-width: 1540px;
  margin: 0 auto;
}

.setup-card {
  overflow: hidden;
}

.setup-heading,
.profile-heading,
.batch-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.setup-heading {
  padding: 24px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--q-secondary) 10%, transparent), transparent 55%), var(--q-card-head);
}

.selection-badge {
  flex: 0 0 auto;
  padding: 6px 9px;
}

.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.profile-option {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  cursor: pointer;
  transition:
    border-color 140ms ease,
    background-color 140ms ease;
}

.profile-option:hover,
.profile-option--selected {
  background: color-mix(in srgb, var(--q-secondary) 7%, transparent);
  border-color: color-mix(in srgb, var(--q-secondary) 62%, transparent);
}

.profile-option--disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.source-input :deep(.q-field__control) {
  cursor: pointer;
}

.profile-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.profile-copy span,
.profile-copy small {
  color: var(--compresso-grey-7);
}

.profile-copy small {
  margin-top: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.batch-toolbar {
  min-height: 48px;
}

.batch-source {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.batch-source span {
  color: var(--compresso-grey-7);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.batch-source strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.winner-handoff {
  border-color: color-mix(in srgb, var(--q-secondary) 55%, var(--border-subtle));
}

@media (max-width: 760px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }

  .setup-heading,
  .profile-heading,
  .batch-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .selection-badge {
    align-self: flex-start;
  }
}
</style>
