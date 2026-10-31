import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { VideoViewer } from './VideoViewer'
import { MediaTimeline } from './MediaTimeline'
import { closestAnalyzedFrame } from '@/lib/videoFrame'
import type { MediaAsset } from '@/types/media'
import type { VideoCaption, VideoFrameResult } from '@/types/video'

const asset: MediaAsset = {
  media_id: 'f2af6ea3-92c0-4eba-9afd-d6a9a225e3a9', original_filename: 'clip.mp4',
  media_type: 'video', detected_mime_type: 'video/mp4', width: 64, height: 48,
  file_size_bytes: 1024, duration_ms: 2000, frame_rate: 4, video_codec: 'h264',
  playback_compatibility: 'likely', created_at: '2026-10-30T00:00:00Z',
  sha256: 'a'.repeat(64), thumbnail_available: false,
}
const frame: VideoFrameResult = {
  frame_id: 'frame', analysis_id: 'analysis', timestamp_ms: 500, source_pts: 2048,
  time_base: '1/4096', source_width: 64, source_height: 48,
  detections: [{ id: 'object', class_id: 0, label: 'person', confidence: 0.9,
    bounding_box: { x: 0.25, y: 0.25, width: 0.5, height: 0.5 }, track_id: 7 }],
  model: { provider: 'ultralytics', name: 'yolo26n.pt', device: 'cpu', version: 'YOLO26', package_version: 'test' },
  inference_ms: 12,
}
const caption: VideoCaption = {
  caption_id: 'caption', analysis_id: 'analysis', frame_id: 'frame', timestamp_ms: 500,
  text: 'A real sampled caption.', edited_text: null, source: 'florence',
  model: { checkpoint: 'Florence', revision: 'test', device: 'cpu', package_version: 'test' },
  inference_ms: 30, created_at: '2026-10-30T00:00:00Z', version: 1,
}

it('selects only nearby analyzed frames and clears boxes in gaps', () => {
  expect(closestAnalyzedFrame([frame], 500, 2)).toEqual(frame)
  expect(closestAnalyzedFrame([frame], 1000, 2)).toBeNull()
  expect(closestAnalyzedFrame([frame], 700, 2)).toEqual(frame)
})

it('synchronizes captions with playback and seeks on external selection', () => {
  const onTimeChange = vi.fn()
  const { rerender } = render(<VideoViewer asset={asset} frames={[frame]} captions={[caption]} onTimeChange={onTimeChange} />)
  const video = screen.getByLabelText('clip.mp4') as HTMLVideoElement
  video.currentTime = 0.5
  fireEvent.timeUpdate(video)
  expect(screen.getByText('A real sampled caption.')).toBeInTheDocument()
  video.currentTime = 1.5
  fireEvent.timeUpdate(video)
  expect(screen.queryByText('A real sampled caption.')).not.toBeInTheDocument()
  rerender(<VideoViewer asset={asset} frames={[frame]} captions={[caption]} seekRequest={{ ms: 500, nonce: 1 }} onTimeChange={onTimeChange} />)
  expect(video.currentTime).toBe(0.5)
  expect(screen.getByText('A real sampled caption.')).toBeInTheDocument()
  expect(onTimeChange).toHaveBeenCalledWith(500)
})

it('clicks a timestamp marker to seek the original video', () => {
  const onSeek = vi.fn()
  render(<MediaTimeline currentTime={0} duration={2} onSeek={onSeek}
    markers={[{ timestampMs: 500, kind: 'caption', title: 'Caption at 0.5s' }]} />)
  const canvas = screen.getByTestId('video-timeline-markers')
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue({
    left: 0, width: 200, top: 0, height: 18, right: 200, bottom: 18, x: 0, y: 0,
    toJSON: () => ({}),
  })
  fireEvent.click(canvas, { clientX: 50 })
  expect(onSeek).toHaveBeenCalledWith(0.5)
  fireEvent.change(screen.getByLabelText('Seek video'), { target: { value: '1.25' } })
  expect(onSeek).toHaveBeenCalledWith(1.25)
})

it('draws normalized boxes at display scale and clears a hidden detection layer', () => {
  const rectangles: Array<[number, number, number, number, number]> = []
  const context = {
    setTransform: vi.fn(), clearRect: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(),
    measureText: vi.fn(() => ({ width: 50 })),
    lineWidth: 0,
    strokeRect(x: number, y: number, width: number, height: number) {
      rectangles.push([x, y, width, height, this.lineWidth])
    },
  }
  const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => context as unknown as CanvasRenderingContext2D)
  try {
    const { rerender } = render(<VideoViewer asset={asset} frames={[frame]} selectedTrackId={7} />)
    const video = screen.getByLabelText('clip.mp4') as HTMLVideoElement
    video.currentTime = 0.5
    fireEvent.timeUpdate(video)
    const [x, y, width, height, lineWidth] = rectangles.at(-1)!
    expect(x).toBeCloseTo(146.67, 1)
    expect(y).toBeCloseTo(110, 1)
    expect(width).toBeCloseTo(293.33, 1)
    expect(height).toBeCloseTo(220, 1)
    expect(lineWidth).toBe(4)
    rectangles.length = 0
    rerender(<VideoViewer asset={asset} frames={[frame]} selectedTrackId={7} showBoxes={false} />)
    expect(rectangles).toHaveLength(0)
  } finally {
    getContext.mockRestore()
  }
})
