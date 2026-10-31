import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LiveCameraInspector, LiveCameraStage } from './LiveCameraWorkspace'
import { useLiveCamera } from './useLiveCamera'
import { uploadMedia } from '@/lib/media'
import type { MediaAsset } from '@/types/media'

vi.mock('@/lib/media', async original => ({
  ...(await original<typeof import('@/lib/media')>()), uploadMedia: vi.fn(),
}))

class FakeSocket {
  static instances: FakeSocket[] = []
  readyState = 1
  bufferedAmount = 0
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  send = vi.fn()
  close = vi.fn(() => { this.readyState = 3; this.onclose?.() })
  constructor(url: string) {
    if (!url.startsWith('ws')) throw new Error('Expected a WebSocket URL')
    FakeSocket.instances.push(this)
  }
  emit(message: object) { this.onmessage?.({ data: JSON.stringify(message) }) }
}

const media: MediaAsset = {
  media_id: 'snapshot', original_filename: 'camera.jpg', media_type: 'image',
  detected_mime_type: 'image/jpeg', width: 640, height: 480, file_size_bytes: 5,
  duration_ms: null, frame_rate: null, video_codec: null, playback_compatibility: null,
  created_at: '2026-10-31T00:00:00Z', sha256: 'a'.repeat(64), thumbnail_available: false,
}
const stopTrack = vi.fn()
const track = { stop: stopTrack, onended: null as (() => void) | null }
const stream = { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream
const onSnapshot = vi.fn()

function Harness({ enabled = true }: { enabled?: boolean }) {
  const camera = useLiveCamera(enabled)
  return <><LiveCameraStage camera={camera} onSnapshot={onSnapshot} />
    <LiveCameraInspector camera={camera} /></>
}

beforeEach(() => {
  vi.clearAllMocks()
  FakeSocket.instances = []
  vi.stubGlobal('WebSocket', FakeSocket)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
    getUserMedia: vi.fn().mockResolvedValue(stream),
    enumerateDevices: vi.fn().mockResolvedValue([{ kind: 'videoinput', deviceId: 'front', label: 'Front camera' }]),
  } })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 640 })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 480 })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn(),
    translate: vi.fn(), scale: vi.fn(),
    setTransform: vi.fn(), clearRect: vi.fn(), strokeRect: vi.fn(), fillRect: vi.fn(),
    fillText: vi.fn(), measureText: vi.fn(() => ({ width: 40 })) } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback => {
    const bytes = new Uint8Array([0xff, 0xd8, 0xff, 0xd9])
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    Object.defineProperty(blob, 'arrayBuffer', { value: async () => bytes.buffer })
    callback(blob)
  })
  vi.mocked(uploadMedia).mockResolvedValue(media)
})

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

async function startCamera() {
  fireEvent.click(screen.getByRole('button', { name: 'Start Camera' }))
  await waitFor(() => expect(FakeSocket.instances).toHaveLength(1))
  const socket = FakeSocket.instances[0]
  act(() => socket.emit({ type: 'session.started', protocol_version: 1,
    session_id: 'session-1', active_sessions: 1, max_width: 640, max_height: 480,
    max_frame_bytes: 1048576, max_fps: 2 }))
  return socket
}

it('starts only on user action, requests no microphone, and releases the stream', async () => {
  render(<Harness />)
  expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()
  const socket = await startCamera()
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith(expect.objectContaining({ audio: false }))
  expect(screen.getByLabelText('Camera device')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Stop Camera' }))
  expect(stopTrack).toHaveBeenCalled()
  expect(socket.close).toHaveBeenCalled()
  expect(screen.getByText('Camera is off')).toBeInTheDocument()
})

it('shows permission errors and cleans up on navigation', async () => {
  vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValueOnce(
    new DOMException('denied', 'NotAllowedError'))
  const view = render(<Harness />)
  fireEvent.click(screen.getByRole('button', { name: 'Start Camera' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Camera permission was denied')
  const socket = await startCamera()
  view.rerender(<Harness enabled={false} />)
  await waitFor(() => expect(socket.close).toHaveBeenCalled())
  expect(stopTrack).toHaveBeenCalled()
})

it('samples one frame in flight and correlates real results before drawing boxes', async () => {
  const view = render(<Harness />)
  const socket = await startCamera()
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 130)) })
  await waitFor(() => expect(socket.send).toHaveBeenCalled())
  const packet = socket.send.mock.calls.find(call => call[0] instanceof ArrayBuffer)?.[0] as ArrayBuffer
  const bytes = new Uint8Array(packet)
  expect(Array.from(bytes.slice(0, 3))).toEqual([0x56, 0x4c, 0x31])
  const length = new DataView(packet).getUint32(3)
  const metadata = JSON.parse(new TextDecoder().decode(bytes.slice(7, 7 + length)))
  expect(metadata.session_id).toBe('session-1')
  expect(metadata.source_width).toBe(640)
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 550)) })
  expect(socket.send.mock.calls.filter(call => call[0] instanceof ArrayBuffer)).toHaveLength(1)
  act(() => socket.emit({ type: 'frame.result', protocol_version: 1,
    session_id: 'wrong-session', frame_id: metadata.frame_id, captured_at_ms: metadata.captured_at_ms,
    source_width: 640, source_height: 480, detections: [], model: {}, inference_ms: 10,
    processing_ms: 11, result_at: new Date().toISOString(), outcome: 'processed' }))
  act(() => socket.emit({ type: 'frame.result', protocol_version: 1,
    session_id: 'session-1', frame_id: 'wrong-frame', captured_at_ms: metadata.captured_at_ms,
    source_width: 640, source_height: 480, detections: [], model: {}, inference_ms: 10,
    processing_ms: 11, result_at: new Date().toISOString(), outcome: 'processed' }))
  expect(screen.getByText('Processed 0')).toBeInTheDocument()
  act(() => socket.emit({ type: 'frame.result', protocol_version: 1,
    session_id: 'session-1', frame_id: metadata.frame_id, captured_at_ms: metadata.captured_at_ms,
    source_width: 640, source_height: 480,
    detections: [{ id: 'det-1', class_id: 0, label: 'person', confidence: 0.9,
      bounding_box: { x: 0.25, y: 0.25, width: 0.5, height: 0.5 } }],
    model: { name: 'yolo26n.pt', device: 'cpu' }, inference_ms: 10,
    processing_ms: 11, result_at: new Date().toISOString(), outcome: 'processed' }))
  expect(screen.getByText('Processed 1')).toBeInTheDocument()
  const hit = screen.getByRole('button', { name: 'Select live person 90 percent' })
  expect(hit).toHaveStyle({ left: '25%', top: '25%', width: '50%', height: '50%' })
  fireEvent.click(hit)
  expect(screen.getByText('Selected: person')).toBeInTheDocument()
  expect(view.container.querySelector('.live-image')).toHaveStyle({ transform: 'translate(-50%, -50%) scaleX(-1)' })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Mirror preview' }))
  expect(view.container.querySelector('.live-image')).toHaveStyle({ transform: 'translate(-50%, -50%)' })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Boxes' }))
  expect(screen.queryByRole('button', { name: 'Select live person 90 percent' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Boxes' }))
  fireEvent.change(screen.getByLabelText('Live display confidence'), { target: { value: '0.95' } })
  expect(screen.queryByRole('button', { name: 'Select live person 90 percent' })).not.toBeInTheDocument()
  view.unmount()
})

it('switches devices by releasing the prior stream and handles socket disconnect', async () => {
  render(<Harness />)
  const first = await startCamera()
  fireEvent.change(screen.getByLabelText('Camera device'), { target: { value: 'front' } })
  await waitFor(() => expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2))
  await waitFor(() => expect(FakeSocket.instances).toHaveLength(2))
  expect(first.close).toHaveBeenCalled()
  expect(stopTrack).toHaveBeenCalled()
  const second = FakeSocket.instances[1]
  act(() => second.emit({ type: 'session.started', protocol_version: 1,
    session_id: 'session-2', active_sessions: 1, max_width: 640, max_height: 480,
    max_frame_bytes: 1048576, max_fps: 2 }))
  act(() => second.close())
  expect(screen.getByRole('alert')).toHaveTextContent('Live connection closed')
  expect(screen.getByRole('button', { name: 'Start Camera' })).toBeInTheDocument()
})

it('keeps the backend model error visible after the socket closes', async () => {
  render(<Harness />)
  const socket = await startCamera()
  act(() => socket.emit({ type: 'session.error', session_id: 'session-1',
    code: 'model_not_installed', message: 'Install YOLO weights.' }))
  act(() => socket.close())
  expect(screen.getByRole('alert')).toHaveTextContent('Install YOLO weights.')
})

it('cancels a pending video frame callback when leaving Live Camera', async () => {
  const request = vi.fn(() => 42)
  const cancel = vi.fn()
  Object.defineProperty(HTMLVideoElement.prototype, 'requestVideoFrameCallback',
    { configurable: true, value: request })
  Object.defineProperty(HTMLVideoElement.prototype, 'cancelVideoFrameCallback',
    { configurable: true, value: cancel })
  try {
    const view = render(<Harness />)
    await startCamera()
    expect(request).toHaveBeenCalled()
    view.rerender(<Harness enabled={false} />)
    await waitFor(() => expect(cancel).toHaveBeenCalledWith(42))
    expect(stopTrack).toHaveBeenCalled()
  } finally {
    delete (HTMLVideoElement.prototype as Partial<HTMLVideoElement>).requestVideoFrameCallback
    delete (HTMLVideoElement.prototype as Partial<HTMLVideoElement>).cancelVideoFrameCallback
  }
})

it('saves an explicit snapshot through the existing media upload API', async () => {
  render(<Harness />)
  await startCamera()
  fireEvent.click(screen.getByRole('button', { name: 'Capture Snapshot' }))
  await waitFor(() => expect(uploadMedia).toHaveBeenCalledWith(
    expect.objectContaining({ name: expect.stringMatching(/^camera-.*\.jpg$/), type: 'image/jpeg' }),
    expect.any(AbortSignal), expect.any(Function)))
  expect(onSnapshot).toHaveBeenCalledWith(media)
})
