import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { getCapabilities, getHealth } from '@/lib/api'
import { getMediaLimits, listMedia, uploadMedia } from '@/lib/media'
import { useMediaStore } from '@/store/media'
import { useThemeStore } from '@/store/theme'
import type { MediaAsset } from '@/types/media'

vi.mock('@/lib/api', () => ({ getHealth: vi.fn(), getCapabilities: vi.fn() }))
vi.mock('@/lib/media', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/media')>()),
  listMedia: vi.fn(), getMediaLimits: vi.fn(), uploadMedia: vi.fn(), deleteMedia: vi.fn(),
}))

const imageAsset: MediaAsset = {
  media_id: 'f2af6ea3-92c0-4eba-9afd-d6a9a225e3a9', original_filename: 'garden.png',
  media_type: 'image', detected_mime_type: 'image/png', width: 1200, height: 800,
  file_size_bytes: 1024, duration_ms: null, frame_rate: null, video_codec: null,
  playback_compatibility: null, created_at: '2026-10-30T00:00:00Z', sha256: 'a'.repeat(64),
  thumbnail_available: true,
}
const videoAsset: MediaAsset = {
  ...imageAsset, media_id: '29ac914e-c899-48d3-8d5b-941f52e8436b', original_filename: 'clip.mp4',
  media_type: 'video', detected_mime_type: 'video/mp4', width: 640, height: 360,
  duration_ms: 5000, frame_rate: 30, video_codec: 'h264', playback_compatibility: 'likely',
}

function renderApp(route = '/workspace/captioning') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>)
  return { ...view, queryClient }
}

describe('VisionLab media workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    useMediaStore.setState({ activeMediaId: null })
    useThemeStore.setState({ theme: 'dark' })
    vi.mocked(getHealth).mockResolvedValue({ status: 'ok', service: 'visionlab-api', version: '0.2.0', environment: 'test' })
    vi.mocked(getCapabilities).mockResolvedValue([
      { id: 'captioning', name: 'Image Captioning', status: 'planned', phase: 4 },
      { id: 'vqa', name: 'Visual Question Answering', status: 'planned', phase: 5 },
      { id: 'analysis', name: 'Image Analysis', status: 'planned', phase: 4 },
      { id: 'objects', name: 'Object and Region Understanding', status: 'planned', phase: 3 },
      { id: 'accessibility', name: 'Accessible Image Descriptions', status: 'planned', phase: 5 },
      { id: 'media_upload', name: 'Media Upload', status: 'available', phase: 2 },
      { id: 'image_preview', name: 'Image Preview', status: 'available', phase: 2 },
      { id: 'video_preview', name: 'Video Preview', status: 'available', phase: 2 },
    ])
    vi.mocked(listMedia).mockResolvedValue([])
    vi.mocked(getMediaLimits).mockResolvedValue({ max_image_bytes: 20971520, max_video_bytes: 262144000, max_video_duration_ms: 600000, max_image_pixels: 40000000 })
  })

  it('keeps the empty state and reports AI capabilities as planned', async () => {
    renderApp()
    expect(await screen.findByText('API connected')).toBeInTheDocument()
    expect(await screen.findByText('Phase 4')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Browse files' })).toBeEnabled()
    expect(screen.getByText('No AI analysis yet')).toBeInTheDocument()
    expect(screen.getByText('Uploaded images and videos will appear here.')).toBeInTheDocument()
  })

  it('uploads an image, previews its metadata, and keeps it across modules', async () => {
    vi.mocked(listMedia).mockResolvedValueOnce([]).mockResolvedValue([imageAsset])
    vi.mocked(uploadMedia).mockResolvedValue(imageAsset)
    const { queryClient } = renderApp()
    await screen.findByText('Uploaded images and videos will appear here.')
    const file = new File(['image bytes'], 'garden.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('Choose an image or video'), { target: { files: [file] } })
    await waitFor(() => expect(uploadMedia).toHaveBeenCalledOnce())
    expect(await screen.findByText('garden.png uploaded and ready.')).toBeInTheDocument()
    expect(useMediaStore.getState().activeMediaId).toBe(imageAsset.media_id)
    expect(queryClient.getQueryData(['media'])).toEqual([imageAsset])
    expect(await screen.findByTestId('image-viewer')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'garden.png' })).toHaveAttribute('src', expect.stringContaining('/media/'))
    expect(screen.getByText('1200 × 800')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: /visual q&a/i }))
    expect(screen.getByTestId('image-viewer')).toBeInTheDocument()
    expect(useMediaStore.getState().activeMediaId).toBe(imageAsset.media_id)
  })

  it('selects a saved video from the recent library and shows playback controls', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset, videoAsset])
    renderApp()
    await screen.findByTestId('image-viewer')
    fireEvent.click(screen.getByRole('button', { name: /clip.mp4 video/i }))
    expect(screen.getByTestId('video-viewer')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Play video' }).length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Seek video')).toBeInTheDocument()
    expect(screen.getByText('30 fps')).toBeInTheDocument()
    expect(useMediaStore.getState().activeMediaId).toBe(videoAsset.media_id)
  })

  it('shows a disconnected state when the backend is unavailable', async () => {
    vi.mocked(getHealth).mockRejectedValue(new Error('offline'))
    renderApp()
    expect(await screen.findByText('API disconnected')).toBeInTheDocument()
    expect(screen.getByText('Backend unavailable')).toBeInTheDocument()
  })

  it('switches theme while preserving current media selection', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    renderApp()
    await screen.findByTestId('image-viewer')
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    await waitFor(() => expect(document.documentElement).toHaveAttribute('data-theme', 'light'))
    expect(screen.getByTestId('image-viewer')).toBeInTheDocument()
  })
})
