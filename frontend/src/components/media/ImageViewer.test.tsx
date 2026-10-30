import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ImageViewer } from './ImageViewer'
import type { MediaAsset } from '@/types/media'

const asset: MediaAsset = {
  media_id: 'f2af6ea3-92c0-4eba-9afd-d6a9a225e3a9', original_filename: 'photo.jpg',
  media_type: 'image', detected_mime_type: 'image/jpeg', width: 1200, height: 800,
  file_size_bytes: 2000, duration_ms: null, frame_rate: null, video_codec: null,
  playback_compatibility: null, created_at: '2026-10-30T00:00:00Z', sha256: 'a'.repeat(64),
  thumbnail_available: true,
}

it('keeps a detection inside the image transform during zoom and pan', () => {
  const onSelect = vi.fn()
  HTMLElement.prototype.setPointerCapture = vi.fn()
  HTMLElement.prototype.hasPointerCapture = vi.fn(() => true)
  HTMLElement.prototype.releasePointerCapture = vi.fn()
  render(<ImageViewer asset={asset} detections={[{ id: 'd1', classId: 0, label: 'person', confidence: 0.9,
    box: { x1: 0.25, y1: 0.2, x2: 0.5, y2: 0.6 } }]} onSelect={onSelect} />)
  const hit = screen.getByRole('button', { name: 'Select person 90 percent' })
  expect(hit).toHaveStyle({ left: '25%', top: '20%', width: '25%', height: '40%' })
  const image = screen.getByRole('img', { name: 'photo.jpg' })
  const layer = image.parentElement as HTMLElement
  expect(hit.parentElement).toBe(layer)
  fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
  expect(layer.style.transform).toContain('scale(1.3)')
  const viewport = layer.parentElement as HTMLElement
  fireEvent(viewport, new MouseEvent('pointerdown', { bubbles: true, clientX: 50, clientY: 60 }))
  fireEvent(viewport, new MouseEvent('pointermove', { bubbles: true, clientX: 80, clientY: 100 }))
  expect(layer.style.transform).toContain('30px')
  expect(layer.style.transform).toContain('40px')
  fireEvent(viewport, new MouseEvent('pointerup', { bubbles: true }))
  fireEvent.click(hit)
  expect(onSelect).toHaveBeenCalledWith('d1')
  expect(hit.parentElement).toBe(layer)
})
