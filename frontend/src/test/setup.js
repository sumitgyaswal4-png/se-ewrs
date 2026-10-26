import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.clearAllMocks()
})

/**
 * Recharts sizes itself from its container, and jsdom reports every
 * element as 0x0 - so without help the charts render an empty SVG and
 * any assertion about their marks would pass vacuously.
 *
 * ResponsiveContainer measures through its own resize detector, which
 * never fires under jsdom, so it is replaced with a fixed-size wrapper.
 * Every other Recharts export stays real, so the tests still exercise
 * the actual chart components rather than a stub of them.
 */
const CHART_WIDTH = 800
const CHART_HEIGHT = 400

vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal()
  const { createElement } = await import('react')
  return {
    ...actual,
    ResponsiveContainer: ({ children }) =>
      createElement(
        'div',
        { style: { width: CHART_WIDTH, height: CHART_HEIGHT } },
        createElement(
          actual.ResponsiveContainer,
          { width: CHART_WIDTH, height: CHART_HEIGHT },
          children,
        ),
      ),
  }
})

global.ResizeObserver = class ResizeObserver {
  constructor(callback) {
    this.callback = callback
  }

  observe(target) {
    // Report a size immediately; Recharts only draws once it has one.
    this.callback(
      [{ target, contentRect: { width: CHART_WIDTH, height: CHART_HEIGHT, top: 0, left: 0 } }],
      this,
    )
  }

  unobserve() {}
  disconnect() {}
}

for (const [property, value] of [
  ['offsetWidth', CHART_WIDTH],
  ['offsetHeight', CHART_HEIGHT],
  ['clientWidth', CHART_WIDTH],
  ['clientHeight', CHART_HEIGHT],
]) {
  Object.defineProperty(HTMLElement.prototype, property, {
    configurable: true,
    value,
  })
}

Object.defineProperty(SVGElement.prototype, 'getBBox', {
  configurable: true,
  value: () => ({ x: 0, y: 0, width: 0, height: 0 }),
})

HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
  return {
    width: CHART_WIDTH,
    height: CHART_HEIGHT,
    top: 0,
    left: 0,
    bottom: CHART_HEIGHT,
    right: CHART_WIDTH,
    x: 0,
    y: 0,
    toJSON: () => {},
  }
}
