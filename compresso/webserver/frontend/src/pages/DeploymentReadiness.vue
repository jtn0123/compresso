<template>
  <q-page padding>
    <div class="q-pa-md readiness-page">
      <PageHeader :title="$t('pages.deploymentReadiness.title')" />

      <AdmonitionBanner
        data-testid="deployment-gate"
        :type="readiness.ready ? 'tip' : 'caution'"
        :title="readiness.ready ? $t('pages.deploymentReadiness.ready') : $t('pages.deploymentReadiness.notReady')"
        class="q-mb-lg"
      >
        {{
          readiness.ready ? $t('pages.deploymentReadiness.readyDetail') : $t('pages.deploymentReadiness.notReadyDetail')
        }}
      </AdmonitionBanner>

      <div v-if="loading" class="row q-col-gutter-md">
        <div v-for="index in 2" :key="index" class="col-12 col-md-6">
          <q-card flat bordered
            ><q-card-section><q-skeleton type="rect" height="180px" /></q-card-section
          ></q-card>
        </div>
      </div>

      <AdmonitionBanner v-else-if="error" type="caution" :title="$t('pages.deploymentReadiness.loadFailed')">
        {{ error }}
      </AdmonitionBanner>

      <template v-else>
        <div class="row q-col-gutter-md">
          <div class="col-12 col-lg-6">
            <q-card flat bordered class="full-height">
              <q-card-section class="row items-center">
                <div class="col">
                  <div class="text-h6">{{ $t('pages.deploymentReadiness.safetyTitle') }}</div>
                  <div class="text-caption text-secondary">
                    {{ $t('pages.deploymentReadiness.safetySubtitle') }}
                  </div>
                </div>
                <q-badge :color="safety.pause_required ? 'negative' : 'positive'">
                  {{
                    safety.pause_required
                      ? $t('pages.deploymentReadiness.paused')
                      : $t('pages.deploymentReadiness.running')
                  }}
                </q-badge>
              </q-card-section>
              <q-separator />
              <q-card-section>
                <div v-if="safety.events?.length" class="column q-gutter-sm">
                  <div
                    v-for="event in safety.events"
                    :key="event.id"
                    :data-testid="`safety-event-${event.id}`"
                    class="nested-card q-pa-md"
                  >
                    <div class="row items-start q-col-gutter-sm">
                      <div class="col">
                        <div class="text-weight-medium">{{ event.message }}</div>
                        <div class="text-caption text-secondary">
                          {{ event.code }} · {{ formatDate(event.first_seen_at) }}
                        </div>
                      </div>
                      <q-badge :color="event.active ? 'negative' : 'grey-7'">
                        {{
                          event.active
                            ? $t('pages.deploymentReadiness.active')
                            : $t('pages.deploymentReadiness.resolved')
                        }}
                      </q-badge>
                    </div>
                    <q-btn
                      v-if="!event.acknowledged_at"
                      :data-testid="`acknowledge-${event.id}`"
                      outline
                      color="secondary"
                      class="q-mt-sm"
                      :label="$t('pages.deploymentReadiness.acknowledgeResolved')"
                      :loading="actionEventId === event.id"
                      @click="acknowledge(event.id)"
                    />
                  </div>
                </div>
                <div v-else class="text-secondary">{{ $t('pages.deploymentReadiness.noSafetyEvents') }}</div>
              </q-card-section>
              <q-card-actions v-if="safety.pause_required" align="right" class="q-pa-md">
                <q-btn
                  data-testid="resume-workers"
                  color="secondary"
                  :label="$t('pages.deploymentReadiness.recheckResume')"
                  :loading="resuming"
                  @click="resumeWorkers"
                />
              </q-card-actions>
            </q-card>
          </div>

          <div class="col-12 col-lg-6">
            <q-card flat bordered class="full-height">
              <q-card-section class="row items-center">
                <div class="col">
                  <div class="text-h6">{{ $t('pages.deploymentReadiness.doctorTitle') }}</div>
                  <div class="text-caption text-secondary">
                    {{ doctorTimestamp }}
                  </div>
                </div>
                <q-badge :color="doctorBadgeColor">{{ doctorStatus }}</q-badge>
              </q-card-section>
              <q-separator />
              <q-card-section>
                <AdmonitionBanner
                  v-if="!readiness.doctor_report || readiness.doctor_report_expired"
                  type="warning"
                  :title="$t('pages.deploymentReadiness.doctorRequired')"
                  class="q-mb-md"
                >
                  {{ $t('pages.deploymentReadiness.doctorRequiredDetail') }}
                </AdmonitionBanner>
                <div v-if="readiness.doctor_report?.checks?.length" class="column q-gutter-sm">
                  <div
                    v-for="check in readiness.doctor_report.checks"
                    :key="check.id || check.name"
                    :data-testid="`doctor-check-${check.id || check.name}`"
                    class="nested-card q-pa-md row items-center"
                  >
                    <q-icon
                      :name="checkIcon(check.status)"
                      :color="checkColor(check.status)"
                      size="sm"
                      class="q-mr-sm"
                    />
                    <div class="col">
                      <div class="text-weight-medium">{{ check.summary || check.name }}</div>
                      <div v-if="check.detail" class="text-caption text-secondary">{{ check.detail }}</div>
                    </div>
                  </div>
                </div>
              </q-card-section>
            </q-card>
          </div>
        </div>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { useI18n } from 'vue-i18n'
import AdmonitionBanner from 'components/ui/AdmonitionBanner.vue'
import PageHeader from 'components/ui/PageHeader.vue'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'

interface SafetyEvent {
  id: string
  message: string
  code: string
  first_seen_at: string
  active: boolean
  acknowledged_at?: string | null
}
interface SafetyState {
  pause_required: boolean
  events: SafetyEvent[]
}
interface DoctorCheck {
  id?: string
  name: string
  status: string
  summary?: string
  detail?: string
}
interface DoctorReport {
  overall_status: string
  generated_at?: string
  checks: DoctorCheck[]
}
interface ReadinessResponse {
  ready: boolean
  doctor_report: DoctorReport | null
  doctor_report_expired: boolean | null
  safety: SafetyState
}

const { t } = useI18n()
const readiness = ref<ReadinessResponse>({
  ready: false,
  doctor_report: null,
  doctor_report_expired: null,
  safety: { pause_required: false, events: [] },
})
const loading = ref(true)
const error = ref('')
const actionEventId = ref('')
const resuming = ref(false)

const safety = computed(() => readiness.value.safety || { pause_required: false, events: [] })
const doctorStatus = computed(() => {
  if (!readiness.value.doctor_report) return t('pages.deploymentReadiness.missing')
  if (readiness.value.doctor_report_expired) return t('pages.deploymentReadiness.expired')
  return String(readiness.value.doctor_report.overall_status || 'unknown').toUpperCase()
})
const doctorBadgeColor = computed(() => {
  if (!readiness.value.doctor_report || readiness.value.doctor_report_expired) return 'warning'
  return readiness.value.doctor_report.overall_status === 'pass' ? 'positive' : 'negative'
})
const doctorTimestamp = computed(() => {
  const generated = readiness.value.doctor_report?.generated_at
  return generated ? t('pages.deploymentReadiness.generatedAt', { date: formatDate(generated) }) : ''
})

function formatDate(value: string | number | undefined): string {
  if (!value) return t('pages.deploymentReadiness.unknownTime')
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function checkColor(status: string): string {
  return status === 'pass' ? 'positive' : status === 'warn' ? 'warning' : 'negative'
}

function checkIcon(status: string): string {
  return status === 'pass' ? 'check_circle' : status === 'warn' ? 'warning' : 'cancel'
}

async function refresh() {
  try {
    error.value = ''
    const response = await axios.get<ReadinessResponse>(getCompressoApiUrl('v2', 'system/readiness'))
    readiness.value = response.data
  } catch (requestError) {
    const responseError = axios.isAxiosError<{ error?: string }>(requestError)
      ? requestError.response?.data.error
      : undefined
    error.value = responseError || t('pages.deploymentReadiness.loadFailedDetail')
  } finally {
    loading.value = false
  }
}

async function acknowledge(eventId: string): Promise<void> {
  actionEventId.value = eventId
  try {
    await axios.post(getCompressoApiUrl('v2', 'system/safety/acknowledge'), {
      event_id: eventId,
      actor: 'operator',
    })
    await refresh()
  } finally {
    actionEventId.value = ''
  }
}

async function resumeWorkers() {
  resuming.value = true
  try {
    await axios.post(getCompressoApiUrl('v2', 'system/safety/resume'), {})
    await refresh()
  } catch (requestError) {
    const responseError = axios.isAxiosError<{ error?: string }>(requestError)
      ? requestError.response?.data.error
      : undefined
    error.value = responseError || t('pages.deploymentReadiness.resumeFailed')
  } finally {
    resuming.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.readiness-page {
  max-width: 1440px;
  margin: 0 auto;
}

@media (max-width: 1023px) {
  .readiness-page {
    padding: 8px;
  }
}
</style>
