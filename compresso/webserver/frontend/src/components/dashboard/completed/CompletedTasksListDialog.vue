<template>
  <CompressoDialogWindow ref="dialogRef" :title="t('headers.completedTasks')" @hide="onDialogHide">
    <div class="completed-tasks-dialog">
      <div class="completed-tasks-table-actions-bar q-pa-sm">
        <div class="row q-col-gutter-sm items-center completed-tasks-toolbar">
          <div v-if="showActionsToggle" class="col-12 row items-center justify-end">
            <CompressoListActionButton
              :icon="actionsExpanded ? 'expand_less' : 'expand_more'"
              :tooltip="
                actionsExpanded
                  ? t('components.completedTasks.hideActions')
                  : t('components.completedTasks.showActions')
              "
              @click="toggleActionsExpanded"
            />
          </div>
          <q-slide-transition>
            <div v-show="actionsExpanded" class="col-12">
              <div class="row q-col-gutter-sm completed-tasks-actions-panel">
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
                  <div class="row items-center q-col-gutter-sm completed-tasks-action-row">
                    <div class="col-auto">
                      <CompressoStandardButton
                        :color="filterButtonColor"
                        icon="filter_list"
                        :label="t('components.completedTasks.filters')"
                        :size="filterSortButtonSize"
                        @click="openFilterDialog"
                      />
                    </div>

                    <div class="col-auto">
                      <CompressoStandardButton
                        :color="sortButtonColor"
                        icon="sort"
                        :icon-right="sortDirectionIcon"
                        :label="sortButtonLabel"
                        :size="filterSortButtonSize"
                        @click="openSortDialog"
                      />
                    </div>

                    <div class="col-auto">
                      <CompressoStandardButton
                        color="secondary"
                        icon="data_object"
                        :label="t('components.completedTasks.metadataBrowserTitle')"
                        :size="filterSortButtonSize"
                        @click="openMetadataBrowser"
                      />
                    </div>

                    <q-space />

                    <div class="col-auto">
                      <CompressoStandardButtonDropdown
                        class="completed-tasks-options-button"
                        :label="t('navigation.options')"
                        :size="filterSortButtonSize"
                      >
                        <q-list>
                          <q-item clickable v-close-popup @click="selectLibraryForRecreateTask">
                            <q-item-section>
                              <q-item-label>
                                <q-icon name="add" />
                                {{ t('components.completedTasks.addToPendingTasksList') }}
                              </q-item-label>
                            </q-item-section>
                          </q-item>

                          <q-separator />

                          <q-item clickable v-close-popup @click="deleteSelected">
                            <q-item-section>
                              <q-item-label>
                                <q-icon name="delete_outline" />
                                {{ t('components.completedTasks.removeSelected') }}
                              </q-item-label>
                            </q-item-section>
                          </q-item>
                        </q-list>
                      </CompressoStandardButtonDropdown>
                    </div>
                  </div>
                </div>

                <div v-if="activeFilterChips.length" class="col-12">
                  <div class="row items-center q-col-gutter-sm completed-tasks-filter-indicator">
                    <div class="col-auto text-secondary completed-tasks-filter-indicator__label">
                      <q-icon name="filter_list" class="q-mr-xs" />
                      {{ t('components.completedTasks.filtersActive') }}
                    </div>
                    <div class="col">
                      <div class="row items-center">
                        <q-chip
                          v-for="chip in activeFilterChips"
                          :key="chip.key"
                          dense
                          outline
                          color="secondary"
                          class="completed-tasks-filter-chip"
                        >
                          {{ chip.label }}
                        </q-chip>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="col-12">
                  <div class="row items-center q-col-gutter-sm completed-tasks-selection">
                    <div class="col-auto">
                      <q-checkbox
                        :model-value="allPageSelected"
                        @update:model-value="toggleSelectPage"
                        color="secondary"
                        :label="t('components.completedTasks.selectPage')"
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
        scroller-id="completed-tasks-scroller"
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
        :selection-clear-label="t('components.completedTasks.selectionBanner.clearSelection')"
        :empty-label="t('headers.listEmpty')"
        :error-label="t('components.completedTasks.errorFetchingList')"
        :retry-label="t('buttons.retry')"
        :load-more-label="t('components.completedTasks.loadMore')"
        :scroll-to-top-label="t('components.completedTasks.scrollToTop')"
        @select-all-matching="selectAllMatchingResults"
        @clear-selection="clearSelection"
        @retry="fetchCompletedTasks({ reset: true })"
        @load-more="loadMore"
        @scroll="handleTableScroll"
        @scroll-top="scrollToTop"
      >
        <template #body="slotProps">
          <q-tr :props="slotProps" class="completed-task-row">
            <q-td auto-width class="completed-task-select">
              <div class="completed-task-cell-center">
                <q-checkbox
                  color="secondary"
                  :model-value="isRowSelected(slotProps.row)"
                  @update:model-value="(value) => toggleRowSelection(slotProps.row, value)"
                />
              </div>
            </q-td>

            <q-td>
              <div class="completed-task-name">{{ slotProps.row.name }}</div>
              <div class="text-caption">
                <span class="text-weight-medium"> {{ t('components.completedTasks.columns.completed') }}: </span>
                {{ slotProps.row.dateTimeCompleted }}
              </div>
              <div class="text-caption">
                <span class="text-weight-medium"> {{ t('components.completedTasks.columns.status') }}: </span>
                <q-badge :color="slotProps.row.status ? 'positive' : 'negative'">
                  {{ slotProps.row.status ? t('status.success') : t('status.failed') }}
                </q-badge>
              </div>
            </q-td>

            <q-td auto-width class="completed-task-actions">
              <div class="completed-task-cell-center">
                <div class="completed-task-action-group">
                  <CompressoStandardButton
                    v-if="$q.screen.gt.xs"
                    :label="t('components.completedTasks.details')"
                    style="min-width: 100px"
                    @click="openDetailsDialog(slotProps.row.id)"
                  />
                  <CompressoListActionButton
                    v-else
                    icon="info"
                    :tooltip="t('components.completedTasks.details')"
                    @click="openDetailsDialog(slotProps.row.id)"
                  />

                  <CompressoStandardButton
                    v-if="$q.screen.gt.xs && slotProps.row.hasMetadata"
                    :label="t('components.completedTasks.metadata')"
                    style="min-width: 120px"
                    @click="openMetadataDialog(slotProps.row.id)"
                  />
                  <CompressoListActionButton
                    v-else-if="slotProps.row.hasMetadata"
                    icon="data_object"
                    :tooltip="t('components.completedTasks.metadata')"
                    @click="openMetadataDialog(slotProps.row.id)"
                  />
                </div>
              </div>
            </q-td>
          </q-tr>
        </template>
      </TaskListTableShell>
    </div>

    <q-dialog v-model="filterDialogOpen" backdrop-filter="blur(2px)">
      <q-card class="completed-tasks-dialog-card" flat bordered>
        <q-card-section class="bg-card-head completed-tasks-dialog-header row items-center justify-between no-wrap">
          <div class="text-h6 text-primary">
            {{ t('components.completedTasks.filtersTitle') }}
          </div>
        </q-card-section>

        <q-separator />

        <q-card-section class="completed-tasks-dialog-body scroll q-pa-lg q-gutter-md">
          <div class="text-subtitle2 text-secondary">
            {{ t('components.completedTasks.filterStatusLabel') }}
          </div>
          <q-btn-toggle v-model="draftStatusFilter" toggle-color="secondary" :options="statusFilterOptions" />

          <div class="text-subtitle2 text-secondary">
            {{ t('components.completedTasks.since') }}
          </div>
          <div class="row items-center q-col-gutter-sm">
            <div class="col">
              <q-input outlined dense debounce="300" color="secondary" v-model="draftSinceDate">
                <template #prepend>
                  <q-icon name="event" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-date v-model="draftSinceDate" mask="YYYY-MM-DD HH:mm" flat bordered>
                        <div class="row items-center justify-end">
                          <CompressoStandardButton v-close-popup :label="sincePopupActionLabel" color="secondary" />
                        </div>
                      </q-date>
                    </q-popup-proxy>
                  </q-icon>
                </template>

                <template #append>
                  <q-icon name="access_time" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-time v-model="draftSinceDate" mask="YYYY-MM-DD HH:mm" format24h flat bordered>
                        <div class="row items-center justify-end">
                          <CompressoStandardButton v-close-popup :label="sincePopupActionLabel" color="secondary" />
                        </div>
                      </q-time>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
            </div>
            <div class="col-auto">
              <CompressoListActionButton
                icon="clear"
                color="secondary"
                :disable="!draftSinceDate"
                :tooltip="draftSinceDate ? t('components.completedTasks.clearSinceFilter') : ''"
                @click="draftSinceDate = null"
              />
            </div>
          </div>

          <div class="text-subtitle2 text-secondary">
            {{ t('components.completedTasks.before') }}
          </div>
          <div class="row items-center q-col-gutter-sm">
            <div class="col">
              <q-input outlined dense debounce="300" color="secondary" v-model="draftBeforeDate">
                <template #prepend>
                  <q-icon name="event" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-date v-model="draftBeforeDate" mask="YYYY-MM-DD HH:mm" flat bordered>
                        <div class="row items-center justify-end">
                          <CompressoStandardButton v-close-popup :label="beforePopupActionLabel" color="secondary" />
                        </div>
                      </q-date>
                    </q-popup-proxy>
                  </q-icon>
                </template>

                <template #append>
                  <q-icon name="access_time" class="cursor-pointer">
                    <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                      <q-time v-model="draftBeforeDate" mask="YYYY-MM-DD HH:mm" format24h flat bordered>
                        <div class="row items-center justify-end">
                          <CompressoStandardButton v-close-popup :label="beforePopupActionLabel" color="secondary" />
                        </div>
                      </q-time>
                    </q-popup-proxy>
                  </q-icon>
                </template>
              </q-input>
            </div>
            <div class="col-auto">
              <CompressoListActionButton
                icon="clear"
                color="secondary"
                :disable="!draftBeforeDate"
                :tooltip="draftBeforeDate ? t('components.completedTasks.clearBeforeFilter') : ''"
                @click="draftBeforeDate = null"
              />
            </div>
          </div>

          <div class="text-caption text-italic text-secondary">
            {{ t('components.completedTasks.filtersHint') }}
          </div>
        </q-card-section>

        <q-card-actions align="between">
          <CompressoStandardButton
            color="secondary"
            :label="t('components.completedTasks.clear')"
            @click="clearFilterDrafts"
          />
          <CompressoStandardButton
            color="secondary"
            :label="t('components.completedTasks.apply')"
            v-close-popup
            @click="applyFilterDrafts"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="sortDialogOpen" backdrop-filter="blur(2px)">
      <q-card class="completed-tasks-dialog-card" flat bordered>
        <q-card-section class="bg-card-head completed-tasks-dialog-header row items-center justify-between no-wrap">
          <div class="text-h6 text-primary">
            {{ t('components.completedTasks.sortTitle') }}
          </div>
        </q-card-section>

        <q-separator />

        <q-card-section class="completed-tasks-dialog-body scroll q-pa-lg q-gutter-md">
          <q-list bordered separator>
            <q-item clickable v-ripple @click="toggleDraftSort('finish_time')">
              <q-item-section>{{ t('components.completedTasks.columns.completed') }}</q-item-section>
              <q-item-section side>
                <q-icon
                  :name="draftSortBy === 'finish_time' ? (draftDescending ? 'arrow_downward' : 'arrow_upward') : 'sort'"
                  :color="draftSortBy === 'finish_time' ? 'secondary' : 'grey-5'"
                />
              </q-item-section>
            </q-item>
            <q-item clickable v-ripple @click="toggleDraftSort('task_label')">
              <q-item-section>{{ t('components.completedTasks.columns.name') }}</q-item-section>
              <q-item-section side>
                <q-icon
                  :name="draftSortBy === 'task_label' ? (draftDescending ? 'arrow_downward' : 'arrow_upward') : 'sort'"
                  :color="draftSortBy === 'task_label' ? 'secondary' : 'grey-5'"
                />
              </q-item-section>
            </q-item>
            <q-item clickable v-ripple @click="toggleDraftSort('task_success')">
              <q-item-section>{{ t('components.completedTasks.columns.status') }}</q-item-section>
              <q-item-section side>
                <q-icon
                  :name="
                    draftSortBy === 'task_success' ? (draftDescending ? 'arrow_downward' : 'arrow_upward') : 'sort'
                  "
                  :color="draftSortBy === 'task_success' ? 'secondary' : 'grey-5'"
                />
              </q-item-section>
            </q-item>
          </q-list>
          <div class="text-caption text-italic text-secondary">
            {{ t('components.completedTasks.sortHint') }}
          </div>
        </q-card-section>

        <q-card-actions align="between">
          <CompressoStandardButton
            color="secondary"
            :label="t('components.completedTasks.clear')"
            @click="clearSortDrafts"
          />
          <CompressoStandardButton
            color="secondary"
            :label="t('components.completedTasks.apply')"
            v-close-popup
            @click="applySortDrafts"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="deleteDialogOpen" backdrop-filter="blur(2px)">
      <q-card class="completed-tasks-dialog-card" flat bordered>
        <q-card-section class="bg-card-head completed-tasks-dialog-header row items-center justify-between no-wrap">
          <div class="text-h6 text-primary">
            {{ t('components.completedTasks.metadataDeleteTitle') }}
          </div>
        </q-card-section>

        <q-separator />

        <q-card-section class="completed-tasks-dialog-body q-pa-lg q-gutter-md">
          <div>{{ t('components.completedTasks.metadataDeletePrompt') }}</div>
          <div v-if="selectAllMatching" class="text-secondary">
            {{ t('components.completedTasks.metadataDeleteAllFilteredNotice') }}
          </div>
        </q-card-section>

        <q-card-actions align="between">
          <CompressoStandardButton
            color="secondary"
            :label="t('navigation.cancel')"
            @click="deleteDialogOpen = false"
          />
          <div class="row items-center q-gutter-sm">
            <CompressoStandardButton
              color="secondary"
              :label="t('components.completedTasks.metadataDeleteTasksOnly')"
              @click="confirmDeleteSelected(false)"
            />
            <CompressoStandardButton
              color="secondary"
              :label="t('components.completedTasks.metadataDeleteTasksAndMetadata')"
              :disable="selectAllMatching"
              @click="confirmDeleteSelected(true)"
            />
          </div>
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="selectLibrary" persistent>
      <q-card class="select-library-card" flat bordered>
        <q-card-section>
          <div class="text-h6 text-primary">{{ t('headers.selectLibrary') }}</div>
        </q-card-section>

        <q-card-section class="q-pt-none">
          <q-select
            outlined
            dense
            color="secondary"
            emit-value
            map-options
            v-model="selectedLibraryId"
            :options="libraryOptions"
            :label="t('components.completedTasks.selectLibraryToAdd')"
          />
        </q-card-section>

        <q-card-actions align="right">
          <CompressoStandardButton color="secondary" :label="t('navigation.cancel')" v-close-popup />
          <CompressoStandardButton
            @click="addSelectedToPendingTaskList"
            color="secondary"
            :label="t('navigation.submit')"
            v-close-popup
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </CompressoDialogWindow>

  <FileMetadataDetailsDialog ref="metadataDialogRef" :completed-task-id="metadataDialogTaskId" />

  <FileMetadataListDialog ref="metadataBrowserRef" />
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import axios from 'axios'
import { getCompressoApiUrl } from 'src/js/compressoGlobals'
import dateTools from 'src/js/dateTools'
import { useMobile } from 'src/composables/useMobile'
import { useTaskDialogScroll } from 'src/composables/useTaskDialogScroll'
import { useTaskListController } from 'src/composables/useTaskListController'
import CompressoDialogWindow from 'components/ui/dialogs/CompressoDialogWindow.vue'
import TaskListTableShell from 'components/dashboard/shared/TaskListTableShell.vue'
import CompletedTaskLogDialog from 'components/dashboard/completed/CompletedTaskLogDialog.vue'
import FileMetadataDetailsDialog from 'components/dashboard/completed/FileMetadataDetailsDialog.vue'
import FileMetadataListDialog from 'components/dashboard/completed/FileMetadataListDialog.vue'
import CompressoStandardButton from 'components/ui/buttons/CompressoStandardButton.vue'
import CompressoListActionButton from 'components/ui/buttons/CompressoListActionButton.vue'
import CompressoStandardButtonDropdown from 'components/ui/buttons/CompressoStandardButtonDropdown.vue'

const props = defineProps({
  initStatusFilter: {
    type: String,
    default: 'all',
  },
})

const emit = defineEmits(['hide'])

const { t } = useI18n()
const $q = useQuasar()
const { isMobile } = useMobile()

const dialogRef = ref(null)
const metadataDialogRef = ref(null)
const metadataDialogTaskId = ref('')
const metadataBrowserRef = ref(null)
const taskListShellRef = ref(null)
const tableWrapperRef = computed(() => taskListShellRef.value?.tableWrapperRef ?? null)
const showScrollTop = ref(false)

const searchValue = ref('')
const statusFilter = ref('all')
const draftStatusFilter = ref('all')
const sinceDate = ref(null)
const beforeDate = ref(null)
const draftSinceDate = ref(null)
const draftBeforeDate = ref(null)
const sortBy = ref('finish_time')
const draftSortBy = ref('finish_time')
const descending = ref(true)
const draftDescending = ref(true)

const filterDialogOpen = ref(false)
const sortDialogOpen = ref(false)
const deleteDialogOpen = ref(false)

const actionsExpanded = ref(true)

const selectLibrary = ref(false)
const selectedLibraryId = ref(null)
const libraryOptions = ref([])

const columns = computed(() => [
  {
    name: 'select',
    label: '',
    field: 'id',
    sortable: false,
  },
  {
    name: 'name',
    label: t('components.completedTasks.columns.name'),
    field: 'name',
    sortable: false,
  },
  {
    name: 'completed',
    label: t('components.completedTasks.columns.completed'),
    field: 'dateTimeCompleted',
    sortable: false,
  },
  {
    name: 'status',
    label: t('components.completedTasks.columns.status'),
    field: 'status',
    sortable: false,
  },
  {
    name: 'actions',
    label: '',
    field: 'id',
    sortable: false,
  },
])

const statusFilterOptions = computed(() => [
  {
    label: t('status.all'),
    value: 'all',
  },
  {
    label: t('status.success'),
    value: 'success',
  },
  {
    label: t('status.failed'),
    value: 'failed',
  },
])

const filterSortButtonSize = computed(() => ($q.screen.width < 450 ? 'sm' : 'md'))

const filterSortActiveColor = 'warning'

const searchLabelColor = computed(() => (searchValue.value.trim().length > 0 ? filterSortActiveColor : 'secondary'))

const showActionsToggle = computed(() => $q.screen.width < 1024 || ($q.screen.width >= 1024 && $q.screen.height < 800))

const { handleTableScroll, scrollToTop } = useTaskDialogScroll({
  tableWrapperRef,
  showScrollTop,
  actionsExpanded,
  showActionsToggle,
})

const sincePopupActionLabel = computed(() =>
  draftSinceDate.value ? t('components.completedTasks.apply') : t('navigation.close'),
)

const beforePopupActionLabel = computed(() =>
  draftBeforeDate.value ? t('components.completedTasks.apply') : t('navigation.close'),
)

const activeFilterChips = computed(() => {
  const chips = []

  if (statusFilter.value !== 'all') {
    const statusLabel =
      statusFilterOptions.value.find((option) => option.value === statusFilter.value)?.label || statusFilter.value
    chips.push({
      key: 'status',
      label: t('components.completedTasks.filterStatus', { status: statusLabel }),
    })
  }

  if (sinceDate.value) {
    chips.push({
      key: 'since',
      label: t('components.completedTasks.filterSince', { date: sinceDate.value }),
    })
  }

  if (beforeDate.value) {
    chips.push({
      key: 'before',
      label: t('components.completedTasks.filterBefore', { date: beforeDate.value }),
    })
  }

  return chips
})

const hasSearch = computed(() => searchValue.value.trim().length > 0)
const hasFilters = computed(() => statusFilter.value !== 'all' || !!sinceDate.value || !!beforeDate.value)

const filterButtonColor = computed(() => (hasFilters.value ? filterSortActiveColor : 'secondary'))

const isDefaultSort = computed(() => sortBy.value === 'finish_time' && descending.value === true)

const sortButtonColor = computed(() => (isDefaultSort.value ? 'secondary' : filterSortActiveColor))

const sortFieldLabel = computed(() => {
  if (sortBy.value === 'task_label') {
    return t('components.completedTasks.columns.name')
  }
  if (sortBy.value === 'task_success') {
    return t('components.completedTasks.columns.status')
  }
  return t('components.completedTasks.columns.completed')
})

const sortDirectionIcon = computed(() => (descending.value ? 'arrow_downward' : 'arrow_upward'))

const sortButtonLabel = computed(() =>
  t('components.completedTasks.sortByActive', {
    field: sortFieldLabel.value,
  }),
)

const buildFiltersPayload = () => ({
  search_value: searchValue.value,
  status: statusFilter.value,
  after: sinceDate.value,
  before: beforeDate.value,
})

const fetchCompletedPage = async ({ start, length }) => {
  const response = await axios({
    method: 'post',
    url: getCompressoApiUrl('v2', 'history/tasks'),
    data: {
      start,
      length,
      ...buildFiltersPayload(),
      order_by: sortBy.value,
      order_direction: descending.value ? 'desc' : 'asc',
    },
  })
  return {
    total: response.data.recordsFiltered,
    rows: response.data.results.map((result) => ({
      id: result.id,
      name: result.task_label,
      dateTimeCompleted: dateTools.printDateTimeString(result.finish_time),
      status: result.task_success,
      hasMetadata: result.has_metadata,
    })),
  }
}

const notifyFetchError = () =>
  $q.notify({
    color: 'negative',
    position: 'top',
    message: t('components.completedTasks.errorFetchingList'),
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
  fetchTasks: fetchCompletedTasks,
  loadMore,
} = useTaskListController({
  fetchPage: fetchCompletedPage,
  buildFiltersPayload,
  onFetchError: notifyFetchError,
})

const selectionBannerPageText = computed(() =>
  t('components.completedTasks.selectionBanner.pageSelected', { count: rows.value.length }),
)

const selectionBannerSelectAllLabel = computed(() => {
  if (hasSearch.value) {
    return t('components.completedTasks.selectionBanner.selectAllMatchingSearch', { count: totalCount.value })
  }
  if (hasFilters.value) {
    return t('components.completedTasks.selectionBanner.selectAllMatchingFilters', { count: totalCount.value })
  }
  return t('components.completedTasks.selectionBanner.selectAll', { count: totalCount.value })
})

const selectionBannerAllSelectedText = computed(() => {
  if (hasSearch.value) {
    return t('components.completedTasks.selectionBanner.allSelectedSearch', { count: totalCount.value })
  }
  if (hasFilters.value) {
    return t('components.completedTasks.selectionBanner.allSelectedFilters', { count: totalCount.value })
  }
  return t('components.completedTasks.selectionBanner.allSelected', { count: totalCount.value })
})

let reloadInterval = null

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

const openFilterDialog = () => {
  draftStatusFilter.value = statusFilter.value
  draftSinceDate.value = sinceDate.value
  draftBeforeDate.value = beforeDate.value
  filterDialogOpen.value = true
}

const openSortDialog = () => {
  draftSortBy.value = sortBy.value
  draftDescending.value = descending.value
  sortDialogOpen.value = true
}

const clearFilterDrafts = () => {
  draftStatusFilter.value = 'all'
  draftSinceDate.value = null
  draftBeforeDate.value = null
}

const applyFilterDrafts = () => {
  statusFilter.value = draftStatusFilter.value
  sinceDate.value = draftSinceDate.value
  beforeDate.value = draftBeforeDate.value
}

const clearSortDrafts = () => {
  draftSortBy.value = 'finish_time'
  draftDescending.value = true
}

const applySortDrafts = () => {
  sortBy.value = draftSortBy.value
  descending.value = draftDescending.value
}

const toggleDraftSort = (option) => {
  if (draftSortBy.value === option) {
    draftDescending.value = !draftDescending.value
  } else {
    draftSortBy.value = option
    draftDescending.value = true
  }
}

const deleteSelected = () => {
  if (selectedCount.value === 0) {
    $q.notify({
      color: 'warning',
      position: 'top',
      message: t('components.completedTasks.nothingSelected'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
    return
  }

  const selectionHasMetadata =
    selectAllMatching.value || rows.value.some((row) => selectedIds.value.includes(row.id) && row.hasMetadata)

  if (selectionHasMetadata) {
    deleteDialogOpen.value = true
    return
  }

  performDeleteSelected(false)
}

const performDeleteSelected = (deleteMetadata) => {
  const data = getSelectionPayload()

  const deleteTasks = () =>
    axios({
      method: 'delete',
      url: getCompressoApiUrl('v2', 'history/tasks'),
      data,
    })

  const deleteMetadataForSelection = async () => {
    if (selectAllMatching.value) {
      return false
    }

    const fingerprints = new Set()
    const requests = selectedIds.value.map((id) =>
      axios({
        method: 'post',
        url: getCompressoApiUrl('v2', 'metadata/by-task'),
        data: {
          task_id: Number(id),
        },
      }),
    )

    const responses = await Promise.all(requests)
    responses.forEach((response) => {
      ;(response.data.results || []).forEach((entry) => {
        if (entry.fingerprint) {
          fingerprints.add(entry.fingerprint)
        }
      })
    })

    const deleteRequests = Array.from(fingerprints).map((fingerprint) =>
      axios({
        method: 'delete',
        url: getCompressoApiUrl('v2', 'metadata'),
        data: {
          fingerprint,
        },
      }),
    )

    await Promise.all(deleteRequests)
    return true
  }

  const run = async () => {
    if (deleteMetadata) {
      try {
        await deleteMetadataForSelection()
      } catch (error) {
        $q.notify({
          color: 'negative',
          position: 'top',
          message: t('components.completedTasks.metadataErrorDelete'),
          icon: 'report_problem',
          actions: [{ icon: 'close', color: 'white' }],
        })
      }
    }

    deleteTasks()
      .then(() => {
        resetSelection()
        fetchCompletedTasks({ reset: true })
      })
      .catch(() => {
        $q.notify({
          color: 'negative',
          position: 'top',
          message: t('components.completedTasks.errorDeleteSelected'),
          icon: 'report_problem',
          actions: [{ icon: 'close', color: 'white' }],
        })
      })
  }

  run()
}

const confirmDeleteSelected = (deleteMetadata) => {
  deleteDialogOpen.value = false
  performDeleteSelected(deleteMetadata)
}

const selectLibraryForRecreateTask = () => {
  axios({
    method: 'get',
    url: getCompressoApiUrl('v2', 'settings/libraries'),
  })
    .then((response) => {
      const libraryPathsList = []
      let defaultSelection
      for (let i = 0; i < response.data.libraries.length; i++) {
        const libraryPath = response.data.libraries[i]
        if (typeof defaultSelection === 'undefined') {
          defaultSelection = libraryPath.id
        }
        libraryPathsList.push({
          label: libraryPath.name,
          value: libraryPath.id,
        })
      }
      libraryOptions.value = libraryPathsList

      selectedLibraryId.value = 1
      if (libraryPathsList.length === 1) {
        selectedLibraryId.value = defaultSelection
        addSelectedToPendingTaskList()
      } else {
        selectLibrary.value = true
      }
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

const addSelectedToPendingTaskList = () => {
  if (selectedCount.value === 0) {
    $q.notify({
      color: 'warning',
      position: 'top',
      message: t('components.completedTasks.nothingSelected'),
      icon: 'report_problem',
      actions: [{ icon: 'close', color: 'white' }],
    })
    return
  }

  const data = {
    ...getSelectionPayload(),
    library_id: selectedLibraryId.value,
  }

  axios({
    method: 'post',
    url: getCompressoApiUrl('v2', 'history/reprocess'),
    data,
  })
    .then(() => {
      resetSelection()
      fetchCompletedTasks({ reset: true })
    })
    .catch(() => {
      $q.notify({
        color: 'negative',
        position: 'top',
        message: t('components.completedTasks.errorAddSelected'),
        icon: 'report_problem',
        actions: [{ icon: 'close', color: 'white' }],
      })
    })
}

const openDetailsDialog = (id) => {
  $q.dialog({
    component: CompletedTaskLogDialog,
    componentProps: {
      completedTaskId: id,
    },
  })
}

const openMetadataDialog = (id) => {
  metadataDialogTaskId.value = String(id)
  nextTick(() => {
    if (metadataDialogRef.value) {
      metadataDialogRef.value.show()
    }
  })
}

const openMetadataBrowser = () => {
  nextTick(() => {
    if (metadataBrowserRef.value) {
      metadataBrowserRef.value.show()
    }
  })
}

watch(statusFilter, () => {
  resetSelection()
  fetchCompletedTasks({ reset: true })
})

watch(sinceDate, () => {
  resetSelection()
  fetchCompletedTasks({ reset: true })
})

watch(beforeDate, () => {
  resetSelection()
  fetchCompletedTasks({ reset: true })
})

watch(searchValue, () => {
  resetSelection()
  fetchCompletedTasks({ reset: true })
})

watch(sortBy, () => {
  fetchCompletedTasks({ reset: true })
})

watch(descending, () => {
  fetchCompletedTasks({ reset: true })
})

onMounted(() => {
  statusFilter.value = props.initStatusFilter

  actionsExpanded.value = true

  fetchCompletedTasks({ reset: true })

  reloadInterval = setInterval(() => {
    if (!loadingMore.value) {
      fetchCompletedTasks({ refreshTop: true, silent: true })
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
.completed-tasks-dialog {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
}

.completed-tasks-table-actions-bar {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--q-card-head);
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  min-width: 0;
}

.q-dark .completed-tasks-table-actions-bar {
  background: var(--q-card-head) !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.completed-tasks-selection {
  padding-left: 17px;
}

@media (min-width: 601px) {
  .completed-tasks-selection {
    margin-top: 8px;
  }
}

.completed-tasks-filter-indicator {
  min-width: 0;
  padding: 2px 0;
}

.completed-tasks-filter-indicator__label {
  display: flex;
  align-items: center;
  white-space: nowrap;
}

.completed-tasks-filter-chip {
  max-width: 100%;
}

.completed-tasks-filter-chip :deep(.q-chip__content) {
  line-height: 1.2;
  padding: 1px 0;
}

.completed-tasks-toolbar {
  width: 100%;
}

.completed-task-row :deep(.q-td) {
  vertical-align: top;
}

.completed-task-select,
.completed-task-actions {
  vertical-align: middle;
}

.completed-task-cell-center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}

.completed-task-action-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.completed-task-name {
  font-weight: 500;
}

.completed-task-actions {
  align-items: center;
  min-width: 0;
  max-width: 100%;
}

@media (max-width: 1023px) {
  .completed-task-action-group {
    flex-direction: row;
    gap: 6px;
  }
}

.select-library-card {
  width: 100%;
  max-width: 420px;
}

.completed-tasks-dialog-card {
  width: 100%;
  max-width: 520px;
}

.completed-tasks-dialog-header {
  position: sticky;
  top: 0;
  z-index: 2;
}

.completed-tasks-dialog-body {
  max-height: 60vh;
}

@media (max-width: 599px) {
  .select-library-card {
    max-width: 95vw;
  }

  .completed-tasks-dialog-card {
    max-width: 95vw;
  }
}

@media (max-width: 449px) {
  .completed-tasks-filter-indicator {
    align-items: flex-start;
  }

  .completed-tasks-filter-indicator__label {
    width: 100%;
  }

  .completed-tasks-action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .completed-tasks-action-row .q-btn,
  .completed-tasks-action-row .completed-tasks-options-button {
    width: 100%;
  }
}
</style>
