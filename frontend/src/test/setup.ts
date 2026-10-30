import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
  value: vi.fn(() => ({ setTransform: vi.fn(), clearRect: vi.fn(), strokeRect: vi.fn() })),
})
Object.defineProperty(HTMLMediaElement.prototype, 'pause', { value: vi.fn() })
Object.defineProperty(HTMLMediaElement.prototype, 'play', { value: vi.fn().mockResolvedValue(undefined) })

afterEach(() => cleanup())

