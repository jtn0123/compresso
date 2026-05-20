import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Capture the callbacks passed to onMounted / onUnmounted so we can drive the
// lifecycle manually from inside the test. We mock these because we're not
// rendering an actual component.
const mountedCallbacks = []
const unmountedCallbacks = []

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual,
    onMounted: (cb) => {
      mountedCallbacks.push(cb)
    },
    onUnmounted: (cb) => {
      unmountedCallbacks.push(cb)
    },
  }
})

// Mock the router so the navigation chords can be observed.
const pushMock = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

import { useKeyboardShortcuts } from '../useKeyboardShortcuts'

function mount() {
  const result = useKeyboardShortcuts()
  // Simulate Vue lifecycle: fire any onMounted callbacks queued by this call.
  while (mountedCallbacks.length) {
    const cb = mountedCallbacks.shift()
    cb()
  }
  return result
}

function unmount() {
  // Simulate component teardown by firing the queued onUnmounted callbacks.
  while (unmountedCallbacks.length) {
    const cb = unmountedCallbacks.shift()
    cb()
  }
}

function dispatch(key, { target } = {}) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true })
  if (target) {
    // KeyboardEvent.target is read-only; override via defineProperty.
    Object.defineProperty(event, 'target', { value: target })
  }
  document.dispatchEvent(event)
  return event
}

describe('useKeyboardShortcuts', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    pushMock.mockClear()
    mountedCallbacks.length = 0
    unmountedCallbacks.length = 0
  })

  afterEach(() => {
    // Clean up any remaining listeners so tests stay isolated.
    unmount()
    vi.useRealTimers()
  })

  describe('chord shortcuts (g + key)', () => {
    it('fires the chord when the second key is pressed within 800ms', () => {
      mount()
      dispatch('g')
      vi.advanceTimersByTime(200)
      dispatch('d')

      expect(pushMock).toHaveBeenCalledOnce()
      expect(pushMock).toHaveBeenCalledWith('/ui/dashboard')
    })

    it('does not fire the chord when the second key arrives after the 800ms window', () => {
      mount()
      dispatch('g')
      // Advance past the 800ms chord window.
      vi.advanceTimersByTime(1000)
      dispatch('d')

      expect(pushMock).not.toHaveBeenCalled()
    })

    it('supports all registered navigation chords', () => {
      mount()
      const chords = [
        ['c', '/ui/compression'],
        ['a', '/ui/approval'],
        ['h', '/ui/health'],
        ['p', '/ui/preview'],
        ['s', '/ui/settings-library'],
        ['w', '/ui/settings-workers'],
      ]
      for (const [second, expectedPath] of chords) {
        pushMock.mockClear()
        dispatch('g')
        vi.advanceTimersByTime(10)
        dispatch(second)
        expect(pushMock).toHaveBeenCalledWith(expectedPath)
      }
    })
  })

  describe('typing-in-form suppression', () => {
    it('does not capture chords while focus is inside an <input>', () => {
      mount()
      const input = document.createElement('input')
      document.body.appendChild(input)
      try {
        dispatch('g', { target: input })
        vi.advanceTimersByTime(50)
        dispatch('d', { target: input })
        expect(pushMock).not.toHaveBeenCalled()
      } finally {
        input.remove()
      }
    })

    it('does not capture chords while focus is inside a <textarea>', () => {
      mount()
      const ta = document.createElement('textarea')
      document.body.appendChild(ta)
      try {
        dispatch('g', { target: ta })
        vi.advanceTimersByTime(50)
        dispatch('d', { target: ta })
        expect(pushMock).not.toHaveBeenCalled()
      } finally {
        ta.remove()
      }
    })
  })

  describe('? toggles help dialog and Escape closes it', () => {
    it('? toggles showHelp', () => {
      const { showHelp } = mount()
      expect(showHelp.value).toBe(false)
      dispatch('?')
      expect(showHelp.value).toBe(true)
      dispatch('?')
      expect(showHelp.value).toBe(false)
    })

    it('Escape closes the help dialog when open', () => {
      const { showHelp } = mount()
      dispatch('?')
      expect(showHelp.value).toBe(true)
      dispatch('Escape')
      expect(showHelp.value).toBe(false)
    })

    it('Escape is a no-op when the help dialog is not open', () => {
      const { showHelp } = mount()
      expect(showHelp.value).toBe(false)
      dispatch('Escape')
      expect(showHelp.value).toBe(false)
    })
  })

  describe('listener cleanup on unmount', () => {
    it('removes the keydown listener so subsequent keys do not fire chords', () => {
      mount()
      // Sanity check: chord works while mounted.
      dispatch('g')
      vi.advanceTimersByTime(10)
      dispatch('d')
      expect(pushMock).toHaveBeenCalledOnce()

      pushMock.mockClear()
      unmount()

      // After unmount, the listener should be detached -- keys must not fire chords.
      dispatch('g')
      vi.advanceTimersByTime(10)
      dispatch('d')
      expect(pushMock).not.toHaveBeenCalled()
    })

    it('calls document.removeEventListener on unmount', () => {
      const removeSpy = vi.spyOn(document, 'removeEventListener')
      mount()
      unmount()
      expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
      removeSpy.mockRestore()
    })
  })
})
