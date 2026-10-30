import { formatTime } from '@/lib/media'
import type { TimestampedAnalysisResult } from '@/types/media'

interface Props {
  currentTime: number
  duration: number
  onSeek: (seconds: number) => void
  markers?: TimestampedAnalysisResult[]
}

export function MediaTimeline({ currentTime, duration, onSeek, markers = [] }: Props) {
  return <div className="media-timeline">
    <span>{formatTime(currentTime)}</span>
    <div className="timeline-track"><input type="range" min={0} max={duration || 1} step={0.01} value={Math.min(currentTime, duration || 1)} onChange={(event) => onSeek(Number(event.target.value))} aria-label="Seek video" disabled={duration <= 0} />
      {markers.map((marker) => <span key={marker.timestampMs} className="timeline-marker" style={{ left: `${duration ? marker.timestampMs / (duration * 1000) * 100 : 0}%` }} aria-hidden="true" />)}
    </div>
    <span>{formatTime(duration)}</span>
  </div>
}
