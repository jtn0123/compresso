export function useTaskDialogScroll({ tableWrapperRef, showScrollTop, actionsExpanded, showActionsToggle }) {
  const handleTableScroll = (event) => {
    const wrapper = event?.target || tableWrapperRef.value
    if (!wrapper) {
      return
    }
    showScrollTop.value = wrapper.scrollTop > 120
    if (showActionsToggle.value && actionsExpanded.value && wrapper.scrollTop > 4) {
      actionsExpanded.value = false
    }
  }

  const scrollToTop = () => {
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
