<template>
  <div class="task-list-shell">
    <q-slide-transition>
      <div v-show="selectionVisible" class="row items-center q-pa-sm task-list-selection-banner">
        <div class="task-list-selection-banner__center">
          <div class="task-list-selection-banner__content">
            <template v-if="showSelectAllPrompt">{{ selectionPageText }}</template>
            <template v-else>{{ selectionAllText }}</template>
          </div>
          <div class="task-list-selection-banner__actions">
            <CompressoStandardButton
              v-if="showSelectAllPrompt"
              outline
              color="secondary"
              dense
              :label="selectionSelectAllLabel"
              @click="$emit('select-all-matching')"
            />
            <CompressoStandardButton
              v-else
              outline
              color="secondary"
              dense
              :label="selectionClearLabel"
              @click="$emit('clear-selection')"
            />
          </div>
        </div>
      </div>
    </q-slide-transition>

    <div :id="scrollerId" ref="tableWrapperRef" class="task-list-table-wrapper" @scroll.passive="onScroll">
      <div class="task-list-body q-pa-sm">
        <div v-if="error && rows.length === 0" class="task-list-state text-negative">
          <q-icon size="2em" name="error_outline" />
          <div>{{ errorLabel }}</div>
          <CompressoStandardButton color="secondary" :label="retryLabel" @click="$emit('retry')" />
        </div>

        <q-infinite-scroll
          v-else
          ref="infiniteScrollRef"
          :disable="allLoaded"
          :offset="200"
          :scroll-target="`#${scrollerId}`"
          @load="(index, done) => $emit('load-more', index, done)"
        >
          <q-table
            flat
            bordered
            hide-header
            hide-pagination
            :rows-per-page-options="[0]"
            row-key="id"
            :rows="rows"
            :columns="columns"
            class="task-list-table"
          >
            <template #body="slotProps">
              <slot name="body" v-bind="slotProps" />
            </template>

            <template #no-data>
              <div class="full-width row flex-center text-accent q-gutter-sm task-list-empty-state">
                <q-icon size="2em" name="sentiment_dissatisfied" />
                <q-item-label>{{ emptyLabel }}</q-item-label>
                <q-icon size="2em" name="priority_high" />
              </div>
            </template>
          </q-table>

          <template #loading>
            <div class="row flex-center q-my-md">
              <q-spinner-dots size="32px" color="secondary" />
            </div>
          </template>
        </q-infinite-scroll>

        <div v-if="!allLoaded && rows.length > 0" class="row justify-center q-mt-md">
          <CompressoStandardButton color="secondary" :label="loadMoreLabel" @click="manualLoadMore" />
        </div>

        <q-inner-loading :showing="loading && rows.length === 0">
          <q-spinner-dots size="42px" color="secondary" />
        </q-inner-loading>

        <div v-show="showScrollTop" class="task-list-scroll-top">
          <q-btn
            flat
            dense
            round
            color="secondary"
            icon="keyboard_arrow_up"
            :aria-label="scrollToTopLabel"
            :title="scrollToTopLabel"
            @click="$emit('scroll-top')"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { PropType } from 'vue'
import type { QTableColumn } from 'quasar'
import CompressoStandardButton from 'components/ui/buttons/CompressoStandardButton.vue'

defineProps({
  rows: { type: Array as PropType<unknown[]>, required: true },
  columns: { type: Array as PropType<QTableColumn[]>, required: true },
  loading: { type: Boolean, default: false },
  allLoaded: { type: Boolean, default: true },
  error: { type: [Error, Object, String], default: null },
  showScrollTop: { type: Boolean, default: false },
  selectionVisible: { type: Boolean, default: false },
  showSelectAllPrompt: { type: Boolean, default: false },
  selectionPageText: { type: String, default: '' },
  selectionAllText: { type: String, default: '' },
  selectionSelectAllLabel: { type: String, default: '' },
  selectionClearLabel: { type: String, default: '' },
  emptyLabel: { type: String, required: true },
  errorLabel: { type: String, required: true },
  retryLabel: { type: String, required: true },
  loadMoreLabel: { type: String, required: true },
  scrollToTopLabel: { type: String, required: true },
  scrollerId: { type: String, required: true },
})

const emit = defineEmits(['load-more', 'select-all-matching', 'clear-selection', 'retry', 'scroll', 'scroll-top'])

const infiniteScrollRef = ref<{ trigger(): void } | null>(null)
const tableWrapperRef = ref<HTMLElement | null>(null)

const manualLoadMore = () => infiniteScrollRef.value?.trigger()
const onScroll = (event: Event): void => emit('scroll', event)

defineExpose({ tableWrapperRef, manualLoadMore })
</script>

<style scoped>
.task-list-shell {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.task-list-selection-banner {
  border-bottom: 1px solid var(--q-separator-color);
  background: rgba(0, 0, 0, 0.03);
  gap: 12px;
}

.q-dark .task-list-selection-banner {
  background: rgba(255, 255, 255, 0.06);
}

.task-list-selection-banner__center {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.task-list-selection-banner__content {
  min-width: 0;
}

.task-list-selection-banner__actions {
  display: flex;
  align-items: center;
}

.task-list-table-wrapper {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: auto;
}

.task-list-body {
  position: relative;
  min-width: 0;
}

.task-list-table {
  width: 100%;
  min-width: 0;
}

.task-list-table :deep(table) {
  width: 100%;
  min-width: 0;
}

.task-list-table :deep(.q-td) {
  white-space: normal;
  overflow-wrap: anywhere;
}

.task-list-state {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
}

.task-list-scroll-top {
  position: sticky;
  bottom: 18px;
  display: flex;
  justify-content: center;
  pointer-events: none;
  padding: 0 18px 12px;
}

.task-list-scroll-top :deep(.q-btn) {
  pointer-events: auto;
}

@media (max-width: 449px) {
  .task-list-selection-banner,
  .task-list-selection-banner__center {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 599px) {
  .task-list-body {
    padding-right: 0;
    padding-left: 0;
  }
}
</style>
