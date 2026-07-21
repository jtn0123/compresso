import type { Ref } from 'vue'

interface TaskDialogScrollOptions {
  tableWrapperRef: Ref<ScrollTarget | null>
  showScrollTop: Ref<boolean>
  actionsExpanded: Ref<boolean>
  showActionsToggle: Ref<boolean>
}

interface ScrollTarget {
  scrollTop: number
  scrollTo(options: ScrollToOptions): void
}

function isScrollTarget(value: unknown): value is ScrollTarget {
  return typeof value === 'object' && value !== null && typeof (value as { scrollTop?: unknown }).scrollTop === 'number'
}

export function useTaskDialogScroll(options: TaskDialogScrollOptions) {
  const { tableWrapperRef, showScrollTop, actionsExpanded, showActionsToggle } = options
  const handleTableScroll = (event?: Event): void => {
    const wrapper = isScrollTarget(event?.target) ? event.target : tableWrapperRef.value
    if (!wrapper) {
      return
    }
    showScrollTop.value = wrapper.scrollTop > 120
    if (showActionsToggle.value && actionsExpanded.value && wrapper.scrollTop > 4) {
      actionsExpanded.value = false
    }
  }

  const scrollToTop = (): void => {
    const wrapper = tableWrapperRef.value
    if (!wrapper) {
      return
    }
    wrapper.scrollTo({ top: 0, behavior: 'smooth' })
    showScrollTop.value = false
  }

  return {
    handleTableScroll,
    scrollToTop,
  }
}
