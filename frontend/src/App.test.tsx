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
import { describeObject, generateCaption, generateDenseRegions, getCaptionModel, listCaptions } from '@/lib/caption'
import { askVideo, cancelVideoJob, getVideoCaptions, getVideoFrames, getVideoJob, getVideoTimeline, getVideoTracks, listVideoAnalyses, startVideoAnalysis } from '@/lib/video'
import { getVisionProviders, listConversations } from '@/lib/multimodal'
import type { CaptionRecord } from '@/types/caption'
import type { AnalysisRecord } from '@/types/vision'
import type { MediaAsset } from '@/types/media'
import type { VideoAnalysis, VideoJob } from '@/types/video'

vi.mock('@/lib/api', () => ({ getHealth: vi.fn(), getCapabilities: vi.fn() }))
vi.mock('@/lib/media', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/media')>()),
  listMedia: vi.fn(), getMediaLimits: vi.fn(), uploadMedia: vi.fn(), deleteMedia: vi.fn(),
}))
vi.mock('@/lib/vision', () => ({ analyzeImage: vi.fn(), getModels: vi.fn(), listAnalyses: vi.fn() }))
vi.mock('@/lib/caption', () => ({ describeObject: vi.fn(), generateCaption: vi.fn(), generateDenseRegions: vi.fn(), getCaptionModel: vi.fn(), listCaptions: vi.fn() }))
vi.mock('@/lib/video', async (original) => ({ ...(await original<typeof import('@/lib/video')>()), startVideoAnalysis: vi.fn(), cancelVideoJob: vi.fn(), askVideo: vi.fn(), listVideoAnalyses: vi.fn(), getVideoJob: vi.fn(), getVideoFrames: vi.fn(), getVideoTimeline: vi.fn(), getVideoTracks: vi.fn(), getVideoCaptions: vi.fn() }))
vi.mock('@/lib/multimodal', async (original) => ({ ...(await original<typeof import('@/lib/multimodal')>()), listConversations: vi.fn(), getVisionProviders: vi.fn() }))
vi.mock('@/components/live/LiveCameraWorkspace', () => ({
  LiveCameraStage: ({ onSnapshot }: { onSnapshot: (asset: MediaAsset) => void }) =>
    <button type="button" onClick={() => onSnapshot(imageAsset)}>Save test snapshot</button>,
  LiveCameraInspector: () => <p>Live inspector</p>,
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
const savedCaption: CaptionRecord = {
  analysis_id: 'e537cb3a-cef0-44fa-b793-08a5f36db33e', media_id: imageAsset.media_id,
  task: 'short', status: 'completed', created_at: '2026-10-30T00:00:00Z', completed_at: '2026-10-30T00:00:01Z',
  model: { provider: 'transformers', checkpoint: 'florence-community/Florence-2-base-ft', revision: 'pinned', device: 'cpu', package_version: '4.57.6' },
  duration_ms: 80, model_load_ms: 0, inference_ms: 70, text: 'A real model response.', regions: [],
  detection_analysis_id: null, detection_id: null,
}
const videoAnalysis: VideoAnalysis = {
  analysis_id: 'e537cb3a-cef0-44fa-b793-08a5f36db34e', media_id: videoAsset.media_id,
  job_id: 'e537cb3a-cef0-44fa-b793-08a5f36db35e', status: 'completed',
  parameters: { detection_fps: 2, caption_interval_seconds: 10, generate_captions: true,
    track_objects: true, detection: { confidence: 0.25, iou: 0.45, image_size: 640, max_detections: 100 } },
  created_at: '2026-10-30T00:00:00Z', completed_at: '2026-10-30T00:00:02Z',
  duration_ms: 5000, coverage_end_ms: 4500, processed_frames: 10,
  caption_frames: 1, elapsed_ms: 2000, error_code: null,
}
const videoJob: VideoJob = {
  job_id: videoAnalysis.job_id, analysis_id: videoAnalysis.analysis_id,
  media_id: videoAsset.media_id, kind: 'analysis', status: 'completed', stage: 'completed',
  processed_frames: 10, total_frames_estimate: 10, current_timestamp_ms: 4500,
  elapsed_ms: 2000, error_code: null, created_at: '2026-10-30T00:00:00Z',
  updated_at: '2026-10-30T00:00:02Z', revision: 11, target_timestamp_ms: null,
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
      { id: 'captioning', name: 'Image Captioning', status: 'unavailable', phase: 4 },
      { id: 'vqa', name: 'Visual Question Answering', status: 'planned', phase: 5 },
      { id: 'analysis', name: 'Image Analysis', status: 'planned', phase: 4 },
      { id: 'objects', name: 'Object and Region Understanding', status: 'unavailable', phase: 4 },
      { id: 'accessibility', name: 'Accessible Image Descriptions', status: 'planned', phase: 5 },
      { id: 'media_upload', name: 'Media Upload', status: 'available', phase: 2 },
      { id: 'image_preview', name: 'Image Preview', status: 'available', phase: 2 },
      { id: 'video_preview', name: 'Video Preview', status: 'available', phase: 2 },
    ])
    vi.mocked(listMedia).mockResolvedValue([])
    vi.mocked(getMediaLimits).mockResolvedValue({ max_image_bytes: 20971520, max_video_bytes: 262144000, max_video_duration_ms: 600000, max_image_pixels: 40000000 })
    vi.mocked(getModels).mockResolvedValue([{ state: 'ready', name: 'yolo26n.pt', device: 'cpu', detail: null }])
    vi.mocked(listAnalyses).mockResolvedValue([])
    vi.mocked(getCaptionModel).mockResolvedValue({ state: 'installed_not_loaded', name: 'Florence-2', revision: 'pinned', device: null })
    vi.mocked(listCaptions).mockResolvedValue([])
    vi.mocked(listVideoAnalyses).mockResolvedValue([])
    vi.mocked(getVideoJob).mockResolvedValue(videoJob)
    vi.mocked(getVideoFrames).mockResolvedValue([])
    vi.mocked(getVideoTimeline).mockResolvedValue([])
    vi.mocked(getVideoTracks).mockResolvedValue([])
    vi.mocked(getVideoCaptions).mockResolvedValue([])
    vi.mocked(listConversations).mockResolvedValue([])
    vi.mocked(getVisionProviders).mockResolvedValue({
      vqa: { provider: 'openai', state: 'configured', model: 'test' },
      accessibility: { provider: 'openai', state: 'configured', model: 'test' },
    })
  })

  it('keeps the empty state and reports current capability status', async () => {
    renderApp()
    expect(await screen.findByText('API connected')).toBeInTheDocument()
    expect(await screen.findByText('Phase 4')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Browse files' })).toBeEnabled()
    expect(screen.getByText('No captions saved for this image.')).toBeInTheDocument()
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
    fireEvent.click(screen.getByLabelText('person'))
    expect(screen.queryByRole('button', { name: 'Select person 92 percent' })).not.toBeInTheDocument()
    expect(analyzeImage).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Reset visualization controls' }))
    fireEvent.click(screen.getByRole('link', { name: /objects & regions/i }))
    expect(screen.getByRole('button', { name: 'Select person 92 percent' })).toBeInTheDocument()
  })

  it('shows analysis progress and sends changed inference parameters only on a new run', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    let finish!: (record: AnalysisRecord) => void
    vi.mocked(analyzeImage).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
      .mockResolvedValueOnce({ ...savedAnalysis, analysis_id: 'fc69ea26-25f9-456c-a37c-5737ef4d1f4e' })
    renderApp('/workspace/analysis')
    fireEvent.click(await screen.findByRole('button', { name: 'Analyze Image' }))
    expect(await screen.findByRole('progressbar', { name: 'Image analysis in progress' })).toBeInTheDocument()
    finish(savedAnalysis)
    await screen.findByRole('button', { name: 'Re-run Analysis' })
    fireEvent.change(screen.getByLabelText('Inference confidence'), { target: { value: '0.4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Re-run Analysis' }))
    await waitFor(() => expect(analyzeImage).toHaveBeenCalledTimes(2))
    expect(vi.mocked(analyzeImage).mock.calls[1][1].confidence).toBe(0.4)
  })

  it('restores a saved analysis and shows an honest empty result', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    vi.mocked(listAnalyses).mockResolvedValue([{ ...savedAnalysis, detections: [], summary: { total_objects: 0, class_counts: {} } }])
    renderApp('/workspace/analysis')
    expect(await screen.findByText(/No supported objects were detected/)).toBeInTheDocument()
    expect(screen.getAllByText('0', { selector: '.analysis-stats strong' })).toHaveLength(2)
  })

  it('reports unavailable image model while exposing video analysis controls', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset, videoAsset])
    vi.mocked(getModels).mockResolvedValue([{ state: 'not_installed', name: 'yolo26n.pt', device: null, detail: 'Install model weights.' }])
    renderApp('/workspace/analysis')
    expect(await screen.findByText(/Install model weights/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /clip.mp4 video/i }))
    expect(screen.getByRole('button', { name: 'Analyze Video' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Analyze Image' })).not.toBeInTheDocument()
  })

  it('queues video analysis and reopens a saved run', async () => {
    vi.mocked(listMedia).mockResolvedValue([videoAsset])
    vi.mocked(listVideoAnalyses).mockResolvedValue([videoAnalysis])
    vi.mocked(startVideoAnalysis).mockResolvedValue({ ...videoJob, status: 'queued', stage: 'queued' })
    renderApp('/workspace/analysis')
    expect(await screen.findByText(/10 sampled frames/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze Video' })).toBeEnabled()
    fireEvent.change(screen.getByLabelText('Video detection FPS'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Analyze Video' }))
    await waitFor(() => expect(startVideoAnalysis).toHaveBeenCalledWith(videoAsset.media_id,
      expect.objectContaining({ detection_fps: 1 })))
    expect(await screen.findByLabelText('Saved video analysis')).toBeInTheDocument()
  })

  it('selects a saved camera snapshot in the shared image workspace', async () => {
    vi.mocked(listMedia).mockResolvedValueOnce([]).mockResolvedValue([imageAsset])
    renderApp('/workspace/live_camera')
    await screen.findByText('API connected')
    await waitFor(() => expect(listMedia).toHaveBeenCalledTimes(1))
    fireEvent.click(await screen.findByRole('button', { name: 'Save test snapshot' }))
    expect(await screen.findByTestId('image-viewer')).toBeInTheDocument()
    expect(useMediaStore.getState().activeMediaId).toBe(imageAsset.media_id)
  })

  it('shows running video progress, requests cancellation, and allows retry', async () => {
    vi.mocked(listMedia).mockResolvedValue([videoAsset])
    vi.mocked(listVideoAnalyses).mockResolvedValue([{ ...videoAnalysis, status: 'running', processed_frames: 3, coverage_end_ms: 1500 }])
    vi.mocked(getVideoJob).mockResolvedValue({ ...videoJob, status: 'running', stage: 'processing', processed_frames: 3, current_timestamp_ms: 1500 })
    vi.mocked(cancelVideoJob).mockResolvedValue({ ...videoJob, status: 'cancel_requested' })
    vi.mocked(startVideoAnalysis).mockResolvedValue({ ...videoJob, status: 'queued', stage: 'queued' })
    renderApp('/workspace/analysis')
    expect(await screen.findByRole('progressbar', { name: 'Video processing progress' })).toHaveValue(30)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel job' }))
    await waitFor(() => expect(cancelVideoJob).toHaveBeenCalledWith(videoJob.job_id))
    fireEvent.click(screen.getByRole('button', { name: 'Analyze Video' }))
    await waitFor(() => expect(startVideoAnalysis).toHaveBeenCalledWith(videoAsset.media_id, expect.any(Object)))
  })

  it('requires video consent and sends only the selected VQA range', async () => {
    vi.mocked(listMedia).mockResolvedValue([videoAsset])
    vi.mocked(askVideo).mockResolvedValue({ examined_timestamps_ms: [0, 1000], conversation: {
      conversation_id: 'conversation', media_id: videoAsset.media_id,
      created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:01Z', messages: [],
    } })
    renderApp('/workspace/vqa')
    const question = await screen.findByLabelText('Question about video frames')
    fireEvent.change(question, { target: { value: 'What is visible?' } })
    const submit = screen.getByRole('button', { name: 'Ask selected frames' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Video range end'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Allow this video's selected frames/i }))
    fireEvent.click(submit)
    await waitFor(() => expect(askVideo).toHaveBeenCalledWith(videoAsset.media_id,
      'What is visible?', 0, 1000, null, true))
  })

  it('keeps video VQA unavailable when OpenAI is unconfigured', async () => {
    vi.mocked(listMedia).mockResolvedValue([videoAsset])
    vi.mocked(getVisionProviders).mockResolvedValue({
      vqa: { provider: 'openai', state: 'unconfigured', model: 'test' },
      accessibility: { provider: 'openai', state: 'unconfigured', model: 'test' },
    })
    renderApp('/workspace/vqa')
    fireEvent.change(await screen.findByLabelText('Question about video frames'),
      { target: { value: 'What is visible?' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Allow this video's selected frames/i }))
    expect(screen.getByRole('button', { name: 'Ask selected frames' })).toBeDisabled()
    expect(askVideo).not.toHaveBeenCalled()
  })

  it('generates a selected caption mode and restores saved Florence text', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    vi.mocked(generateCaption).mockResolvedValue({ ...savedCaption, task: 'detailed', text: 'A detailed real response.' })
    renderApp()
    await screen.findByTestId('image-viewer')
    fireEvent.change(await screen.findByLabelText('Caption mode'), { target: { value: 'detailed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Caption' }))
    await waitFor(() => expect(generateCaption).toHaveBeenCalledWith(imageAsset.media_id, 'detailed'))
    expect(await screen.findByText('A detailed real response.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Regenerate Caption' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate Caption' }))
    await waitFor(() => expect(generateCaption).toHaveBeenCalledTimes(2))
  })

  it('shows saved dense regions with selectable aligned boxes and an independent layer switch', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    const dense: CaptionRecord = { ...savedCaption, task: 'dense', text: null,
      regions: [{ id: 'region-1', description: 'A person near a bus', model: savedCaption.model,
        bounding_box: { x: 0.25, y: 0.2, width: 0.3, height: 0.5 } }] }
    vi.mocked(listCaptions).mockResolvedValue([dense])
    vi.mocked(generateDenseRegions).mockResolvedValue(dense)
    renderApp()
    const hit = await screen.findByRole('button', { name: 'Select region A person near a bus' })
    expect(hit).toHaveStyle({ left: '25%', top: '20%', width: '30%', height: '50%' })
    fireEvent.click(hit)
    expect(screen.getByText('Normalized box: 0.2500, 0.2000, 0.3000, 0.5000')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show Florence regions' }))
    expect(screen.queryByRole('button', { name: 'Select region A person near a bus' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Generate Dense Regions' }))
    await waitFor(() => expect(generateDenseRegions).toHaveBeenCalledWith(imageAsset.media_id))
  })

  it('describes a selected YOLO object and displays the saved description', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    vi.mocked(listAnalyses).mockResolvedValue([savedAnalysis])
    vi.mocked(describeObject).mockResolvedValue({ ...savedCaption, task: 'selected_object', text: 'A person by a bus.',
      detection_analysis_id: savedAnalysis.analysis_id, detection_id: 'd1' })
    renderApp('/workspace/objects')
    fireEvent.click(await screen.findByRole('button', { name: 'Select person 92 percent' }))
    fireEvent.click(screen.getByRole('button', { name: 'Describe Selected Object' }))
    await waitFor(() => expect(describeObject).toHaveBeenCalledWith(imageAsset.media_id, savedAnalysis.analysis_id, 'd1'))
    expect(await screen.findByText('A person by a bus.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Select person 92 percent' })).toBeInTheDocument()
  })

  it('shows caption progress and a correlated backend error', async () => {
    vi.mocked(listMedia).mockResolvedValue([imageAsset])
    let reject!: (error: Error) => void
    vi.mocked(generateCaption).mockImplementation(() => new Promise((_, rejectPromise) => { reject = rejectPromise }))
    renderApp()
    await screen.findByTestId('image-viewer')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Generate Caption' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Generate Caption' }))
    expect(await screen.findByRole('progressbar', { name: 'Caption generation in progress' })).toBeInTheDocument()
    reject(new Error('Florence is unavailable'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Florence is unavailable')
  })
})
