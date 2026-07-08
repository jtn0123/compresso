import { describe, expect, it } from 'vitest'
import { computed, ref } from 'vue'
import { useTaskDialogScroll } from '../useTaskDialogScroll'

describe('useTaskDialogScroll', () => {
  it('shows the scroll-to-top action after scrolling down', () => {
    const tableWrapperRef = ref(null)
    const showScrollTop = ref(false)
    const actionsExpanded = ref(true)
    const showActionsToggle = computed(() => true)
    const { handleTableScroll } = useTaskDialogScroll({
      tableWrapperRef,
      showScrollTop,
      actionsExpanded,
      showActionsToggle,
    })

    handleTableScroll({ target: { scrollTop: 140 } })

    expect(showScrollTop.value).toBe(true)
    expect(actionsExpanded.value).toBe(false)
  })

  it('scrolls the wrapper back to the top', () => {
    const calls = []
    const tableWrapperRef = ref({
      scrollTo: (payload) => calls.push(payload),
    })
    const showScrollTop = ref(true)
    const actionsExpanded = ref(true)
    const showActionsToggle = computed(() => false)
    const { scrollToTop } = useTaskDialogScroll({
      tableWrapperRef,
      showScrollTop,
      actionsExpanded,
      showActionsToggle,
    })

    scrollToTop()

    expect(calls).toEqual([{ top: 0, behavior: 'smooth' }])
    expect(showScrollTop.value).toBe(false)
  })
})
