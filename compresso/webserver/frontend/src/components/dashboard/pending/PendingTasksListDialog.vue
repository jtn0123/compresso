<template>
  <CompressoDialogWindow ref="dialogRef" :title="t('headers.pendingTasks')" @hide="onDialogHide">
    <div class="pending-tasks-dialog">
      <div class="pending-tasks-table-actions-bar q-pa-sm">
        <div class="row q-col-gutter-sm items-center pending-tasks-toolbar">
          <div v-if="showActionsToggle" class="col-12 row items-center justify-end">
            <CompressoListActionButton
              :icon="actionsExpanded ? 'expand_less' : 'expand_more'"
              :tooltip="
                actionsExpanded ? t('components.pendingTasks.hideActions') : t('components.pendingTasks.showActions')
              "
              @click="toggleActionsExpanded"
            />
          </div>

          <q-slide-transition>
            <div v-show="actionsExpanded" class="col-12">
              <div class="row q-col-gutter-sm pending-tasks-actions-panel">
                <div class="col-12">
                  <q-input
                    outlined
                    dense
                    debounce="300"
                    :color="searchLabelColor"
                    :label-color="searchLabelColor"
                    v-model="searchValue"
                    :placeholder="t('navigation.search')"
                  >
                    <template #append>
                      <q-icon name="search" :color="searchLabelColor" />
                    </template>
                  </q-input>
                </div>

                <div class="col-12">
                  <div class="row items-center q-col-gutter-sm pending-tasks-action-row">
                    <div class="col-auto">
                      <CompressoStandardButton
                        :color="filterButtonColor"
                        icon="filter_list"
                        :label="t('components.pendingTasks.filters')"
                        :size="filterButtonSize"
                        @click="openFilterDialog"
                      />
                    </div>

                    <q-space />
                    <div class="col-auto">
                      <CompressoStandardButtonDropdown
                        class="pending-tasks-options-button"
                        :label="t('navigation.options')"
                        :size="filterButtonSize"
                      >
                        <q-list>
                          <q-item clickable v-close-popup @click="rescanLibrary">
                            <q-item-section>
                              <q-item-label>
                                <q-icon name="search" />
                                {{ t('components.pendingTasks.rescanLibrary') }}
                              </q-item-label>
                            </q-item-section>
                          </q-item>

                          <q-separator />

                          <q-item clickable v-close-popup @click="moveToTop">
                            <q-item-section>
                              <q-item-label>
                                <q-icon name="arrow_upward" />
                                {{ t('components.pendingTasks.moveToTop') }}
                              </q-item-label>
                            </q-item-section>
                          </q-item>

                          <q-item clickable v-close-popup @click="moveToBottom">
                            <q-item-section>
                              <q-item-label>
                                <q-icon name="arrow_downward" />
                                {{ t('components.pendingTasks.moveToBottom') }}
                              </q-item-label>
                            </q-item-section>
                          </q-item>

                          <q-separator />

                          <q-item clickable v-close-popup @click="deleteSelected">
                            <q-item-section>
                              <q-item-label>
                                <q-icon name="delete_outline" />
                                {{ t('components.pendingTasks.removeSelected') }}
                              </q-item-label>
                            </q-item-section>
                          </q-item>
                        </q-list>
                      </CompressoStandardButtonDropdown>
                    </div>
                  </div>
                </div>

                <div v-if="activeFilterChips.length" class="col-12">
                  <div class="row items-center q-col-gutter-sm pending-tasks-filter-indicator">
                    <div class="col-auto text-secondary pending-tasks-filter-indicator__label">
                      <q-icon name="filter_list" class="q-mr-xs" />
                      {{ t('components.pendingTasks.filtersActive') }}
                    </div>
                    <div class="col">
                      <div class="row items-center">
                        <q-chip
                          v-for="chip in activeFilterChips"
                          :key="chip.key"
                          dense
                          outline
                          color="secondary"
                          class="pending-tasks-filter-chip"
                        >
                          {{ chip.label }}
                        </q-chip>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="col-12">
                  <div class="row items-center q-col-gutter-sm pending-tasks-selection">
                    <div class="col-auto">
                      <q-checkbox
                        :model-value="allPageSelected"
                        @update:model-value="toggleSelectPage"
                        color="secondary"
                        :label="t('components.pendingTasks.selectPage')"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </q-slide-transition>
        </div>

        <q-separator class="q-mt-sm" />
      </div>

      <TaskListTableShell
        ref="taskListShellRef"
        scroller-id="pending-tasks-scroller"
        :rows="rows"
        :columns="columns"
        :loading="loading"
        :all-loaded="allLoaded"
        :error="error"
        :is-mobile="isMobile"
        :show-scroll-top="showScrollTop"
        :selection-visible="(allPageSelected || selectAllMatching) && actionsExpanded"
        :show-select-all-prompt="showSelectAllMatchingPrompt"
        :selection-page-text="selectionBannerPageText"
        :selection-all-text="selectionBannerAllSelectedText"
        :selection-select-all-label="selectionBannerSelectAllLabel"
        :selection-clear-label="t('components.pendingTasks.selectionBanner.clearSelection')"
        :empty-label="t('headers.listEmpty')"
        :error-label="t('components.pendingTasks.errorFetchingList')"
        :retry-label="t('buttons.retry')"
        :load-more-label="t('components.pendingTasks.loadMore')"
        :scroll-to-top-label="t('components.pendingTasks.scrollToTop')"
        @select-all-matching="selectAllMatchingResults"
        @clear-selection="clearSelection"
        @retry="fetchPendingTasks({ reset: true })"
        @load-more="loadMore"
        @scroll="handleTableScroll"
        @scroll-top="scrollToTop"
      >
        <template #body="props">
          <q-tr :props="props" class="pending-task-row">
            <q-td auto-width class="pending-task-select">
              <div class="pending-task-cell-center">
                <q-checkbox
                  color="secondary"
                  :model-value="isRowSelected(props.row)"
                  @update:model-value="(value) => toggleRowSelection(props.row, value)"
                />
              </div>
            </q-td>

            <q-td>
              <div class="pending-task-name">{{ props.row.name }}</div>
              <div class="text-caption">
                <span class="text-weight-medium"> {{ t('components.pendingTasks.columns.library') }}: </span>
                {{ props.row.libraryName }}
              </div>
            </q-td>
          </q-tr>
        </template>
      </TaskListTableShell>
    </div>

    <q-dialog v-model="filterDialogOpen" backdrop-filter="blur(2px)">
      <q-card class="pending-tasks-dialog-card" flat bordered>
        <q-card-section class="bg-card-head pending-tasks-dialog-header row items-center justify-between no-wrap">
          <div class="text-h6 text-primary">
            {{ t('components.pendingTasks.filtersTitle') }}
          </div>
        </q-card-section>

        <q-separator />

        <q-card-section class="pending-tasks-dialog-body scroll q-pa-lg q-gutter-md">
          <div class="text-subtitle2 text-secondary">
            {{ t('components.pendingTasks.filterLibrariesLabel') }}
          </div>
          <q-select
            v-if="showLibraryChips"
            outlined
            color="primary"
            multiple
            emit-value
            map-options
            use-chips
            v-model="draftLibraryFilters"
            :options="libraryOptions"
            :label="t('components.pendingTasks.filterLibrariesLabel')"
          />
          <q-select
            v-else
            outlined
            color="primary"
            multiple
            emit-value
            map-options
            v-model="draftLibraryFilters"
            :options="libraryOptions"
            :label="t('components.pendingTasks.filterLibrariesLabel')"
            :display-value="libraryFilterDisplay"
          />
          <div class="text-caption text-italic text-secondary">
            {{ t('components.pendingTasks.filterLibrariesHint') }}
          </div>
        </q-card-section>

        <q-card-actions align="between">
          <CompressoStandardButton
            color="secondary"
            :label="t('components.pendingTasks.clear')"
            @click="clearFilterDrafts"
          />
          <CompressoStandardButton
            color="secondary"
            :label="t('components.pendingTasks.apply')"
            v-close-popup
            @click="applyFilterDrafts"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </CompressoDialogWindow>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import { useMobile } from 'src/composables/useMobile'
import { useTaskDialogScroll } from 'src/composables/useTaskDialogScroll'
import { useTaskListController } from 'src/composables/useTaskListController'
import CompressoDialogWindow from 'components/ui/dialogs/CompressoDialogWindow.vue'
import TaskListTableShell from 'components/dashboard/shared/TaskListTableShell.vue'
import CompressoStandardButton from 'components/ui/buttons/CompressoStandardButton.vue'
import CompressoStandardButtonDropdown from 'components/ui/buttons/CompressoStandardButtonDropdown.vue'
import CompressoListActionButton from 'components/ui/buttons/CompressoListActionButton.vue'

const emit = defineEmits(['hide'])

const { t } = useI18n()
const $q = useQuasar()
const { isMobile } = useMobile()

const dialogRef = ref(null)
const taskListShellRef = ref(null)
const tableWrapperRef = computed(() => taskListShellRef.value?.tableWrapperRef ?? null)
const showScrollTop = ref(false)

const searchValue = ref('')
const libraryFilters = ref([])
const draftLibraryFilters = ref([])
const libraryOptions = ref([])
const filterDialogOpen = ref(false)
const actionsExpanded = ref(true)

let reloadInterval = null

const columns = computed(() => [
  {
    name: 'select',
    label: '',
    field: 'id',
    sortable: false,
  },
  {
    name: 'name',
    label: t('components.pendingTasks.columns.name'),
    field: 'name',
    sortable: false,
  },
  {
    name: 'library',
    label: t('components.pendingTasks.columns.library'),
    field: 'libraryName',
    sortable: false,
  },
])

const showActionsToggle = computed(() => {
  const isNarrow = $q.screen.lt.md
  const isShortWide = !$q.screen.lt.md && $q.screen.height < 800
  return isNarrow || isShortWide
})

const { handleTableScroll, scrollToTop } = useTaskDialogScroll({
  tableWrapperRef,
  showScrollTop,
  actionsExpanded,
  showActionsToggle,
})

const filterSortActiveColor = 'warning'

const searchLabelColor = computed(() => (searchValue.value.trim().length > 0 ? filterSortActiveColor : 'secondary'))

const hasSearch = computed(() => searchValue.value.trim().length > 0)
const hasFilters = computed(() => libraryFilters.value.length > 0)

const filterButtonColor = computed(() => (hasFilters.value ? filterSortActiveColor : 'secondary'))

const filterButtonSize = computed(() => ($q.screen.width < 450 ? 'sm' : 'md'))

const libraryNameById = computed(() =>
  libraryOptions.value.reduce((acc, option) => {
    acc[option.value] = option.label
    return acc
  }, {}),
)

const activeFilterChips = computed(() =>
  libraryFilters.value.map((id) => ({
    key: `library-${id}`,
    label: t('components.pendingTasks.filterLibraryChip', { library: libraryNameById.value[id] || id }),
  })),
)

const showLibraryChips = computed(() => draftLibraryFilters.value.length > 0)

const libraryFilterDisplay = computed(() => {
  if (draftLibraryFilters.value.length === 0) {
    return t('components.pendingTasks.allLibraries')
  }
  return draftLibraryFilters.value.map((id) => libraryNameById.value[id] || id).join(', ')
})

const buildFiltersPayload = () => ({
  search_value: searchValue.value,
  library_ids: libraryFilters.value,
})

const fetchPendingPage = async ({ start, length }) => {
  const response = await axios({
    method: 'post',
    url: getCompressoApiUrl('v2', 'pending/tasks'),
    data: {
      start,
      length,
      ...buildFiltersPayload(),
      order_by: 'priority',
      order_direction: 'desc',
    },
  })
  return {
    total: response.data.recordsFiltered,
    rows: response.data.results.map((result) => ({
      id: result.id,
      name: result.abspath,
      libraryName: result.library_name,
    })),
  }
}

const notifyFetchError = () =>
  $q.notify({
    color: 'negative',
    position: 'top',
    message: t('components.pendingTasks.errorFetchingList'),
    icon: 'report_problem',
    actions: [{ icon: 'close', color: 'white' }],
  })

const {
  loading,
  loadingMore,
  error,
  rows,
  totalCount,
  selectedIds,
  selectAllMatching,
  excludedIds,
  allLoaded,
  allPageSelected,
  selectedCount,
  showSelectAllMatchingPrompt,
  resetSelection,
  clearSelection,
  isRowSelected,
  toggleRowSelection,
  toggleSelectPage,
  selectAllMatchingResults,
  getSelectionPayload,
  fetchTasks: fetchPendingTasks,
  loadMore,
} = useTaskListController({
  fetchPage: fetchPendingPage,
  buildFiltersPayload,
  onFetchError: notifyFetchError,
})

const selectionBannerPageText = computed(() =>
  t('components.pendingTasks.selectionBanner.pageSelected', { count: rows.value.length }),
)

const selectionBannerSelectAllLabel = computed(() => {
  if (hasSearch.value) {
    return t('components.pendingTasks.selectionBanner.selectAllMatchingSearch', { count: totalCount.value })
  }
  if (hasFilters.value) {
    return t('components.pendingTasks.selectionBanner.selectAllMatchingFilters', { count: totalCount.value })
  }
  return t('components.pendingTasks.selectionBanner.selectAll', { count: totalCount.value })
})

const selectionBannerAllSelectedText = computed(() => {
  if (hasSearch.value) {
    return t('components.pendingTasks.selectionBanner.allSelectedSearch', { count: totalCount.value })
  }
  if (hasFilters.value) {
    return t('components.pendingTasks.selectionBanner.allSelectedFilters', { count: totalCount.value })
  }
  return t('components.pendingTasks.selectionBanner.allSelected', { count: totalCount.value })
})

const show = () => {
  dialogRef.value.show()
  showScrollTop.value = false
}

const hide = () => {
  dialogRef.value.hide()
}

const onDialogHide = () => {
  emit('hide')
  showScrollTop.value = false
}

const toggleActionsExpanded = () => {
  actionsExpanded.value = !actionsExpanded.value
}

const fetchLibraryOptions = () => {
  return axios({
    method: 'get',
    url: getCompressoApiUrl('v2', 'settings/libraries'),
  })
    .then((response) => {
      const options = response.data.libraries.map((library) => ({
        label: library.name,
        value: library.id,
      }))
      libraryOptions.value = options
    })
    .catch(() => {
      $q.notify({
        color: 'negative',
        position: 'top',
        message: t('notifications.failedToFetchLibraryList'),
        icon: 'report_problem',
        actions: [{ icon: 'close', color: 'white' }],
      })
    })
}

const openFilterDialog = () => {
  draftLibraryFilters.value = [...libraryFilters.value]
  filterDialogOpen.value = true
  if (libraryOptions.value.length === 0) {
    fetchLibraryOptions()
  }
}

const clearFilterDrafts = () => {
  draftLibraryFilters.value = []
}

const applyFilterDrafts = () => {
  libraryFilters.value = [...draftLibraryFilters.value]
}

const rescanLibrary = () => {
  axios({
    method: 'post',
    url: getCompressoApiUrl('v2', 'pending/rescan'),
  })
    .then(() => {
      $q.notify({
        color: 'positive',
        position: 'top',
        message: t('notifications.rescanLibraryScheduled'),
        icon: 'check_circle',
        actions: [{ icon: 'close', color: 'white' }],
      })
    })
    .catch(() => {
      $q.notify({
        color: 'negative',
        position: 'top',
        message: t('notifications.rescanLibraryError'),
        icon: 'report_problem',
        actions: [{ icon: 'close', color: 'white' }],
      })
    })
}

const moveToTop = () => {
  if (selectedCount.value === 0) {
    $q.notify({
      color: 'warning',
      position: 'top',
      message: t('components.pendingTasks.nothingSelected'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
    return
  }
  moveTo('top')
}

const moveToBottom = () => {
  if (selectedCount.value === 0) {
    $q.notify({
      color: 'warning',
      position: 'top',
      message: t('components.pendingTasks.nothingSelected'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
    return
  }
  moveTo('bottom')
}

const moveTo = (position) => {
  const data = {
    position,
    ...getSelectionPayload(),
  }

  axios({
    method: 'post',
    url: getCompressoApiUrl('v2', 'pending/reorder'),
    data,
  })
    .then(() => {
      resetSelection()
      fetchPendingTasks({ reset: true })
    })
    .catch(() => {
      $q.notify({
        color: 'negative',
        position: 'top',
        message: t('components.pendingTasks.errorReorder'),
        icon: 'report_problem',
        actions: [{ icon: 'close', color: 'white' }],
      })
    })
}

const deleteSelected = () => {
  if (selectedCount.value === 0) {
    $q.notify({
      color: 'warning',
      position: 'top',
      message: t('components.pendingTasks.nothingSelected'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
    return
  }

  const data = getSelectionPayload()
  axios({
    method: 'delete',
    url: getCompressoApiUrl('v2', 'pending/tasks'),
    data,
  })
    .then(() => {
      resetSelection()
      fetchPendingTasks({ reset: true })
    })
    .catch(() => {
      $q.notify({
        color: 'negative',
        position: 'top',
        message: t('components.pendingTasks.errorDeleteSelected'),
        icon: 'report_problem',
        actions: [{ icon: 'close', color: 'white' }],
      })
    })
}

watch(searchValue, () => {
  resetSelection()
  fetchPendingTasks({ reset: true })
})

watch(libraryFilters, () => {
  resetSelection()
  fetchPendingTasks({ reset: true })
})

onMounted(() => {
  actionsExpanded.value = true

  fetchLibraryOptions()

  fetchPendingTasks({ reset: true })

  reloadInterval = setInterval(() => {
    if (!loadingMore.value) {
      fetchPendingTasks({ refreshTop: true, silent: true })
    }
  }, 10000)
})

onBeforeUnmount(() => {
  if (reloadInterval != null) {
    clearInterval(reloadInterval)
  }
})

defineExpose({
  show,
  hide,
})
</script>

<style scoped>
.pending-tasks-dialog {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
}

.pending-tasks-table-actions-bar {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--q-card-head);
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  min-width: 0;
}

.q-dark .pending-tasks-table-actions-bar {
  background: var(--q-card-head) !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.pending-tasks-selection {
  padding-left: 17px;
}

@media (min-width: 601px) {
  .pending-tasks-selection {
    margin-top: 8px;
  }
}

.pending-tasks-filter-indicator {
  min-width: 0;
  padding: 2px 0;
}

.pending-tasks-filter-indicator__label {
  display: flex;
  align-items: center;
  white-space: nowrap;
}

.pending-tasks-filter-chip {
  max-width: 100%;
}

.pending-tasks-filter-chip :deep(.q-chip__content) {
  line-height: 1.2;
  padding: 1px 0;
}

.pending-tasks-toolbar {
  width: 100%;
}

.pending-task-row :deep(.q-td) {
  vertical-align: top;
}

.pending-task-select {
  vertical-align: middle;
}

.pending-task-cell-center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}

.pending-task-name {
  font-weight: 500;
}

.pending-tasks-dialog-card {
  width: 100%;
  max-width: 520px;
}

.pending-tasks-dialog-header {
  position: sticky;
  top: 0;
  z-index: 2;
}

.pending-tasks-dialog-body {
  max-height: 60vh;
}

@media (max-width: 599px) {
  .pending-tasks-dialog-card {
    max-width: 95vw;
  }
}

@media (max-width: 449px) {
  .pending-tasks-filter-indicator {
    align-items: flex-start;
  }

  .pending-tasks-filter-indicator__label {
    width: 100%;
  }

  .pending-tasks-action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .pending-tasks-action-row .q-btn,
  .pending-tasks-action-row .pending-tasks-options-button {
    width: 100%;
  }
}
</style>
