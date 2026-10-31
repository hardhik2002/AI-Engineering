import type { VideoFrameResult } from '@/types/video'

export function closestAnalyzedFrame(frames: VideoFrameResult[], timestampMs: number, fps: number): VideoFrameResult | null {
  const threshold = Math.min(500, 600 / Math.max(fps, 0.25))
  let nearest: VideoFrameResult | null = null
  for (const frame of frames) {
    if (!nearest || Math.abs(frame.timestamp_ms - timestampMs) < Math.abs(nearest.timestamp_ms - timestampMs)) nearest = frame
  }
  return nearest && Math.abs(nearest.timestamp_ms - timestampMs) <= threshold ? nearest : null
}
