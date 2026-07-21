<template>
  <CompressoDialogPopup ref="dialogRef" :title="dialogTitle" @hide="onDialogHide">
    <div class="q-pa-md">
      <q-card flat>
        <q-card-section>
          <q-input disable readonly borderless v-model="currentPath">
            <template #before>
              <q-icon name="folder_open" />
            </template>
          </q-input>
        </q-card-section>

        <q-separator />

        <q-card-section class="q-pa-none">
          <q-list bordered padding>
            <q-item
              v-for="directory in directories"
              :key="directory.full_path"
              clickable
              v-ripple
              @click="fetchDirectoryListing(directory.full_path)"
            >
              <q-item-section avatar>
                <q-icon color="primary" name="folder_open" />
              </q-item-section>
              <q-item-section>
                <q-item-label>{{ directory.name }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
      </q-card>
    </div>
  </CompressoDialogPopup>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import axios from 'axios'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import CompressoDialogPopup from 'components/ui/dialogs/CompressoDialogPopup.vue'
import type { ApiSchema } from 'src/types/contracts'
import type { DialogController } from 'src/types/ui'

interface DirectoryEntry { name: string; full_path: string }

const toDirectoryEntry = (value: Record<string, unknown>): DirectoryEntry | null =>
  typeof value.name === 'string' && typeof value.full_path === 'string'
    ? { name: value.name, full_path: value.full_path }
    : null

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  initialPath: {
    type: String,
    default: '',
  },
  listType: {
    type: String,
    default: 'directories',
  },
})

const emit = defineEmits<{
  hide: []
  selected: [payload: { selectedPath: string }]
}>()

const $q = useQuasar()
const { t } = useI18n()

const dialogRef = ref<DialogController | null>(null)
const isOpen = ref(false)
const currentPath = ref('')
const directories = ref<DirectoryEntry[]>([])
const files = ref<Record<string, unknown>[]>([])

const dialogTitle = computed(() => props.title || t('headers.selectDirectory'))

const fetchDirectoryListing = (path: string): void => {
  currentPath.value = path
  const data = {
    current_path: currentPath.value,
    list_type: props.listType,
  }
  axios<ApiSchema<'DirectoryListingResults'>>({
    method: 'post',
    url: getCompressoApiUrl('v2', 'filebrowser/list'),
    data: data,
  })
    .then((response) => {
      directories.value = response.data.directories
        .map(toDirectoryEntry)
        .filter((entry): entry is DirectoryEntry => entry !== null)
      files.value = response.data.files
    })
    .catch(() => {
      $q.notify({ type: 'negative', message: t('notifications.failedToListDirectory') })
    })
}

const show = () => {
  isOpen.value = true
  dialogRef.value?.show()
  fetchDirectoryListing(props.initialPath)
}

const hide = () => {
  dialogRef.value?.hide()
}

const onDialogHide = () => {
  isOpen.value = false
  emit('selected', { selectedPath: currentPath.value })
  emit('hide')
}

watch(
  () => props.initialPath,
  (value) => {
    if (!value || !isOpen.value) {
      return
    }
    fetchDirectoryListing(value)
  },
)

defineExpose({
  show,
  hide,
})
</script>
