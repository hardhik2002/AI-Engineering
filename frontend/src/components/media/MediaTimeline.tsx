import { useEffect, useRef } from 'react'
import { formatTime } from '@/lib/media'
import { useElementSize } from './useElementSize'
import type { TimestampedAnalysisResult } from '@/types/media'

interface Props {
  currentTime: number
  duration: number
  onSeek: (seconds: number) => void
  markers?: TimestampedAnalysisResult[]
}

export function MediaTimeline({ currentTime, duration, onSeek, markers = [] }: Props) {
  const trackRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const size = useElementSize(trackRef)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !duration) return
    const ratio = window.devicePixelRatio || 1
    canvas.width = Math.max(1, Math.round(size.width * ratio))
    canvas.height = Math.round(18 * ratio)
    const context = canvas.getContext('2d')
    if (!context) return
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, size.width, 18)
    const colors: Record<string, string> = { detection: '#7ce6c4', track: '#aad2ff', caption: '#d5b6ff', vqa: '#f4ad83', coverage: '#566673', failure: '#ed8d83' }
    for (const marker of markers) {
      const x = Math.max(0, Math.min(size.width, marker.timestampMs / (duration * 1000) * size.width))
      context.fillStyle = colors[marker.kind ?? 'coverage']
      context.fillRect(x, marker.kind === 'caption' || marker.kind === 'vqa' ? 1 : 5, marker.kind === 'caption' || marker.kind === 'vqa' ? 3 : 2, marker.kind === 'caption' || marker.kind === 'vqa' ? 16 : 8)
    }
  }, [markers, duration, size.width])
  function clickMarker(event: React.MouseEvent<HTMLCanvasElement>) {
    const bounds = event.currentTarget.getBoundingClientRect()
    if (bounds.width <= 0 || !duration) return
    const requested = Math.max(0, Math.min(duration * 1000, (event.clientX - bounds.left) / bounds.width * duration * 1000))
    const closest = markers.reduce<TimestampedAnalysisResult | null>((best, item) => !best || Math.abs(item.timestampMs - requested) < Math.abs(best.timestampMs - requested) ? item : best, null)
    const near = closest && Math.abs(closest.timestampMs - requested) <= duration * 1000 * 8 / bounds.width
    onSeek((near ? closest.timestampMs : requested) / 1000)
  }
  return <div className="media-timeline">
    <span>{formatTime(currentTime)}</span>
    <div className="timeline-track" ref={trackRef}><input type="range" min={0} max={duration || 1} step={0.01} value={Math.min(currentTime, duration || 1)} onChange={(event) => onSeek(Number(event.target.value))} aria-label="Seek video" disabled={duration <= 0} />
      {markers.length > 0 && <canvas ref={canvasRef} className="timeline-canvas" data-testid="video-timeline-markers" onClick={clickMarker} title="Click a marker to seek; use the slider for keyboard seeking" aria-label="Video analysis markers" />}
    </div>
    <span>{formatTime(duration)}</span>
  </div>
}
