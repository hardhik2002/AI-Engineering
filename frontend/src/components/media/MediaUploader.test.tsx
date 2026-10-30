import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MediaUploader } from './MediaUploader'
import { uploadMedia } from '@/lib/media'
import { mediaErrorMessage } from '@/lib/media'
import { AxiosError, AxiosHeaders } from 'axios'

vi.mock('@/lib/media', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/media')>()), uploadMedia: vi.fn(),
}))

beforeEach(() => vi.clearAllMocks())

it('shows upload progress and lets a user cancel', async () => {
  vi.mocked(uploadMedia).mockImplementation(async (_file, signal, onProgress) => {
    onProgress(42)
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('cancelled'))))
  })
  render(<MediaUploader onUploaded={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Choose an image or video'), {
    target: { files: [new File(['abc'], 'test.png', { type: 'image/png' })] },
  })
  expect(await screen.findByText('42%')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel upload' }))
  expect(await screen.findByText('Upload cancelled.')).toBeInTheDocument()
})

it('shows an upload error and retries the same file', async () => {
  vi.mocked(uploadMedia).mockRejectedValueOnce(new Error('Server error')).mockResolvedValueOnce({
    media_id: 'f2af6ea3-92c0-4eba-9afd-d6a9a225e3a9', original_filename: 'test.png',
    media_type: 'image', detected_mime_type: 'image/png', width: 10, height: 10,
    file_size_bytes: 3, duration_ms: null, frame_rate: null, video_codec: null,
    playback_compatibility: null, created_at: '2026-10-30T00:00:00Z', sha256: 'a'.repeat(64),
    thumbnail_available: true,
  })
  const onUploaded = vi.fn()
  render(<MediaUploader onUploaded={onUploaded} />)
  fireEvent.change(screen.getByLabelText('Choose an image or video'), {
    target: { files: [new File(['abc'], 'test.png', { type: 'image/png' })] },
  })
  expect(await screen.findByText('Server error')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(onUploaded).toHaveBeenCalledOnce())
})

it('includes the backend request ID in an actionable error', () => {
  const error = new AxiosError('failed', 'ERR_BAD_RESPONSE', undefined, undefined, {
    data: { error: { code: 'invalid_media', message: 'Image is malformed.' } },
    status: 422, statusText: 'Unprocessable Content', config: { headers: new AxiosHeaders() },
    headers: new AxiosHeaders({ 'x-request-id': '08a937ff-72d5-4e0d-bbd6-fbf996ca634b' }),
  })
  expect(mediaErrorMessage(error)).toContain('Reference ID: 08a937ff-72d5-4e0d-bbd6-fbf996ca634b')
})
