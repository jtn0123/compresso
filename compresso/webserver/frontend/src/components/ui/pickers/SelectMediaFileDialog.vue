<template>
  <CompressoDialogPopup ref="dialogRef" :title="t('pages.sampleComparison.filePickerTitle')" @hide="onDialogHide">
    <div class="q-pa-md">
      <q-input :model-value="currentPath" readonly outlined dense color="primary" class="q-mb-md">
        <template #prepend><q-icon name="folder_open" /></template>
      </q-input>

      <div v-if="loading" class="row justify-center q-pa-xl">
        <q-spinner color="secondary" size="36px" />
      </div>

      <q-list v-else bordered separator class="media-file-list">
        <q-item
          v-for="directory in visibleDirectories"
          :key="directory.full_path"
          clickable
          @click="openDirectory(directory)"
        >
          <q-item-section avatar><q-icon name="folder" color="secondary" /></q-item-section>
          <q-item-section>{{ directory.name }}</q-item-section>
        </q-item>
        <q-item v-for="file in mediaFiles" :key="file.full_path" clickable @click="selectFile(file)">
          <q-item-section avatar><q-icon name="movie" color="primary" /></q-item-section>
          <q-item-section>
            <q-item-label>{{ file.name }}</q-item-label>
            <q-item-label caption>{{ file.full_path }}</q-item-label>
          </q-item-section>
          <q-item-section side><q-icon name="chevron_right" /></q-item-section>
        </q-item>
        <q-item v-if="visibleDirectories.length === 0 && mediaFiles.length === 0">
          <q-item-section class="text-grey-6">{{ t('pages.sampleComparison.noMediaFiles') }}</q-item-section>
        </q-item>
      </q-list>
    </div>
  </CompressoDialogPopup>
</template>

<script setup>
import { computed, ref } from 'vue'
import axios from 'axios'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import CompressoDialogPopup from 'components/ui/dialogs/CompressoDialogPopup.vue'

const props = defineProps({
  initialPath: { type: String, default: '/' },
})
const emit = defineEmits(['selected', 'hide'])
const $q = useQuasar()
const { t } = useI18n()
const dialogRef = ref(null)
const currentPath = ref('/')
const rootPath = ref('/')
const directories = ref([])
const files = ref([])
const loading = ref(false)
const mediaExtensions = new Set(['.avi', '.m2ts', '.m4v', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.ts', '.webm'])

const mediaFiles = computed(() =>
  files.value.filter((file) => {
    const name = String(file.name || '').toLowerCase()
    return [...mediaExtensions].some((extension) => name.endsWith(extension))
  }),
)
const visibleDirectories = computed(() => directories.value.filter((directory) => isWithinRoot(directory.full_path)))

function normalizePath(path) {
  const normalized = String(path || '/')
    .replaceAll('\\', '/')
    .replace(/\/+$/, '')
  return normalized || '/'
}

function isWithinRoot(path) {
  const root = normalizePath(rootPath.value)
  const candidate = normalizePath(path)
  return root === '/' || candidate === root || candidate.startsWith(`${root}/`)
}

async function fetchDirectory(path) {
  if (!isWithinRoot(path)) return
  loading.value = true
  currentPath.value = path || '/'
  try {
    const response = await axios.post(getCompressoApiUrl('v2', 'filebrowser/list'), {
      current_path: currentPath.value,
      list_type: 'all',
    })
    directories.value = response.data.directories || []
    files.value = response.data.files || []
  } catch {
    $q.notify({ type: 'negative', message: t('notifications.failedToListDirectory') })
  } finally {
    loading.value = false
  }
}

function openDirectory(directory) {
  fetchDirectory(directory.full_path)
}

function selectFile(file) {
  emit('selected', { selectedPath: file.full_path })
  dialogRef.value?.hide()
}

function show() {
  rootPath.value = props.initialPath || '/'
  currentPath.value = rootPath.value
  dialogRef.value?.show()
  fetchDirectory(currentPath.value)
}

function onDialogHide() {
  emit('hide')
}

defineExpose({ show })
</script>

<style scoped>
.media-file-list {
  max-height: min(62vh, 620px);
  overflow-y: auto;
}
</style>
