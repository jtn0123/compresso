import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import TaskListTableShell from '../TaskListTableShell.vue'

const buttonStub = {
  name: 'CompressoStandardButton',
  props: ['label'],
  emits: ['click'],
  template: '<button @click="$emit(\'click\')">{{ label }}</button>',
}

const iconButtonStub = {
  name: 'QBtn',
  emits: ['click'],
  template: '<button @click="$emit(\'click\')" />',
}

const stubs = {
  'q-slide-transition': { template: '<div><slot /></div>' },
  'q-infinite-scroll': {
    methods: {
      trigger() {
        this.$emit('load', 1, vi.fn())
      },
    },
    template: '<div><slot /><slot name="loading" /></div>',
  },
  'q-table': {
    props: ['rows'],
    template:
      '<div><slot v-for="row in rows" name="body" :row="row" /><slot v-if="rows.length === 0" name="no-data" /></div>',
  },
  'q-icon': true,
  'q-item-label': { template: '<span><slot /></span>' },
  'q-spinner-dots': true,
  'q-inner-loading': true,
  'q-btn': iconButtonStub,
  CompressoStandardButton: buttonStub,
}

const mountShell = (props = {}) =>
  mount(TaskListTableShell, {
    props: {
      rows: [{ id: 1 }],
      columns: [],
      emptyLabel: 'Empty',
      errorLabel: 'Failed',
      retryLabel: 'Retry',
      loadMoreLabel: 'More',
      scrollToTopLabel: 'Top',
      scrollerId: 'tasks',
      ...props,
    },
    slots: { body: '<div class="task-row">row</div>' },
    global: { stubs },
  })

const buttonWithLabel = (wrapper, label) =>
  wrapper.findAllComponents({ name: 'CompressoStandardButton' }).find((button) => button.props('label') === label)

describe('TaskListTableShell', () => {
  it('renders task rows and relays scroll events', async () => {
    const wrapper = mountShell()
    await wrapper.find('#tasks').trigger('scroll')
    expect(wrapper.find('.task-row').exists()).toBe(true)
    expect(wrapper.emitted('scroll')).toHaveLength(1)
  })

  it('shows retryable error state when the initial load fails', async () => {
    const wrapper = mountShell({ rows: [], error: new Error('offline') })
    expect(wrapper.text()).toContain('Failed')
    buttonWithLabel(wrapper, 'Retry').vm.$emit('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('supports select-all and clear-selection banner actions', async () => {
    const wrapper = mountShell({
      selectionVisible: true,
      showSelectAllPrompt: true,
      selectionPageText: 'Page selected',
      selectionSelectAllLabel: 'Select all',
    })
    buttonWithLabel(wrapper, 'Select all').vm.$emit('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('select-all-matching')).toHaveLength(1)

    await wrapper.setProps({ showSelectAllPrompt: false, selectionAllText: 'Everything', selectionClearLabel: 'Clear' })
    buttonWithLabel(wrapper, 'Clear').vm.$emit('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('clear-selection')).toHaveLength(1)
  })

  it('exposes manual loading and scroll-to-top behavior', async () => {
    const wrapper = mountShell({ allLoaded: false, showScrollTop: true })
    buttonWithLabel(wrapper, 'More').vm.$emit('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('load-more')).toHaveLength(1)
    wrapper.findComponent({ name: 'QBtn' }).vm.$emit('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('scroll-top')).toHaveLength(1)
  })
})
