import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { getCapabilities, getHealth } from '@/lib/api'
import { getMediaLimits, listMedia, uploadMedia } from '@/lib/media'
import { useMediaStore } from '@/store/media'
import { useThemeStore } from '@/store/theme'
import { analyzeImage, getModels, listAnalyses } from '@/lib/vision'
import type { AnalysisRecord } from '@/types/vision'
import type { MediaAsset } from '@/types/media'

vi.mock('@/lib/api', () => ({ getHealth: vi.fn(), getCapabilities: vi.fn() }))
vi.mock('@/lib/media', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/media')>()),
  listMedia: vi.fn(), getMediaLimits: vi.fn(), uploadMedia: vi.fn(), deleteMedia: vi.fn(),
}))
vi.mock('@/lib/vision', () => ({ analyzeImage: vi.fn(), getModels: vi.fn(), listAnalyses: vi.fn() }))

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
const savedAnalysis: AnalysisRecord = {
  analysis_id: 'e537cb3a-cef0-44fa-b793-08a5f36db32e', media_id: imageAsset.media_id,
  status: 'completed', task: 'object_detection', created_at: '2026-10-30T00:00:00Z', completed_at: '2026-10-30T00:00:01Z',
  model: { provider: 'ultralytics', name: 'yolo26n.pt', device: 'cpu', version: 'YOLO26', package_version: '8.4.193' },
  image: { width: 1200, height: 800, coordinate_space: 'exif_oriented' },
  parameters: { confidence: 0.25, iou: 0.45, image_size: 640, max_detections: 100 },
  detections: [{ id: 'd1', class_id: 0, label: 'person', confidence: 0.92, bounding_box: { x: 0.25, y: 0.2, width: 0.3, height: 0.5 } },
    { id: 'd2', class_id: 2, label: 'car', confidence: 0.48, bounding_box: { x: 0.7, y: 0.3, width: 0.2, height: 0.2 } }],
  summary: { total_objects: 2, class_counts: { person: 1, car: 1 } },
  timings_ms: { preprocessing: 3, inference: 40, postprocessing: 2, total: 45 }, error_code: null,
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
    useMediaStore.setState({ activeMediaId: null, activeAnalysisId: null })
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
    vi.mocked(getModels).mockResolvedValue([{ state: 'ready', name: 'yolo26n.pt', device: 'cpu', detail: null }])
    vi.mocked(listAnalyses).mockResolvedValue([])
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
    expect(localStorage.getItem('visionlab-active-media')).toContain(videoAsset.media_id)
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

  it('runs detection, selects a box, filters saved results and keeps them across modules', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    vi.mocked(analyzeImage).mockResolvedValue(savedAnalysis)
    renderApp('/workspace/analysis')
    fireEvent.click(await screen.findByRole('button', { name: 'Analyze Image' }))
    await waitFor(() => expect(analyzeImage).toHaveBeenCalledOnce())
    await waitFor(() => expect(screen.getAllByText('2', { selector: '.analysis-stats strong' })).toHaveLength(2))
    const hit = screen.getByRole('button', { name: 'Select person 92 percent' })
    expect(hit).toHaveStyle({ left: '25%', top: '20%', width: '30%', height: '50%' })
    fireEvent.click(hit)
    expect(screen.getByText(/Pixels \(x, y, w, h\)/)).toBeInTheDocument()
    expect(screen.getByText('300, 160, 360, 400')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Display confidence'), { target: { value: '0.5' } })
    expect(screen.queryByRole('button', { name: 'Select car 48 percent' })).not.toBeInTheDocument()
    expect(analyzeImage).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('link', { name: /objects & regions/i }))
    expect(screen.getByRole('button', { name: 'Select person 92 percent' })).toBeInTheDocument()
  })

  it('restores a saved analysis and shows an honest empty result', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    vi.mocked(listAnalyses).mockResolvedValue([{ ...savedAnalysis, detections: [], summary: { total_objects: 0, class_counts: {} } }])
    renderApp('/workspace/analysis')
    expect(await screen.findByText(/No supported objects were detected/)).toBeInTheDocument()
    expect(screen.getAllByText('0', { selector: '.analysis-stats strong' })).toHaveLength(2)
  })

  it('reports unavailable model and unsupported video analysis', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset, videoAsset])
    vi.mocked(getModels).mockResolvedValue([{ state: 'not_installed', name: 'yolo26n.pt', device: null, detail: 'Install model weights.' }])
    renderApp('/workspace/analysis')
    expect(await screen.findByText(/Install model weights/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /clip.mp4 video/i }))
    expect(screen.getByText('Video analysis is planned for Phase 6.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Analyze Image' })).not.toBeInTheDocument()
  })
})
