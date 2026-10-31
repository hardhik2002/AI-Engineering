import { useCallback, useEffect, useRef, useState } from 'react'
import { Maximize2, Pause, Play, Volume2, VolumeX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MediaTimeline } from '@/components/media/MediaTimeline'
import { OverlayCanvas } from '@/components/media/OverlayCanvas'
import { useElementSize } from '@/components/media/useElementSize'
import { mediaContentUrl, mediaThumbnailUrl } from '@/lib/media'
import { closestAnalyzedFrame } from '@/lib/videoFrame'
import type { MediaAsset, TimestampedAnalysisResult } from '@/types/media'
import type { VideoCaption, VideoFrameResult } from '@/types/video'

interface Props {
  asset: MediaAsset
  frames?: VideoFrameResult[]
  captions?: VideoCaption[]
  markers?: TimestampedAnalysisResult[]
  analysisFps?: number
  selectedTrackId?: number | null
  displayConfidence?: number
  excludedClasses?: string[]
  showBoxes?: boolean
  showCaptions?: boolean
  showLabels?: boolean
  showConfidence?: boolean
  seekRequest?: { ms: number; nonce: number } | null
  onTimeChange?: (timestampMs: number) => void
}

export function VideoViewer({ asset, frames = [], captions = [], markers = [], analysisFps = 2,
  selectedTrackId = null, displayConfidence = 0, excludedClasses = [], showBoxes = true,
  showCaptions = true, showLabels = true, showConfidence = true, seekRequest = null,
  onTimeChange }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const stage = useElementSize(stageRef)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(asset.duration_ms ? asset.duration_ms / 1000 : 0)
  const [volume, setVolume] = useState(1)
  const [muted, setMuted] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [error, setError] = useState(false)
  const [displaySize, setDisplaySize] = useState({ width: asset.width, height: asset.height })
  const validGeometry = displaySize.width === asset.width && displaySize.height === asset.height
  const fit = Math.min(stage.width / displaySize.width, stage.height / displaySize.height)
  const overlayWidth = Math.max(0, displaySize.width * fit)
  const overlayHeight = Math.max(0, displaySize.height * fit)
  const frame = validGeometry ? closestAnalyzedFrame(frames, currentTime * 1000, analysisFps) : null
  const detections = showBoxes ? (frame?.detections ?? []).filter(item =>
    item.confidence >= displayConfidence && !excludedClasses.includes(item.label)).map(item => ({
      id: item.id, classId: item.class_id, confidence: item.confidence,
      label: `${item.label}${item.track_id === null ? '' : ` #${item.track_id}`}`,
      box: { x1: item.bounding_box.x, y1: item.bounding_box.y,
        x2: item.bounding_box.x + item.bounding_box.width,
        y2: item.bounding_box.y + item.bounding_box.height },
    })) : []
  const selectedId = selectedTrackId === null ? undefined :
    frame?.detections.find(item => item.track_id === selectedTrackId)?.id
  const caption = captions.find(item => Math.abs(item.timestamp_ms - currentTime * 1000) <= 500)
  const notifyRef = useRef(onTimeChange)
  const notifiedMsRef = useRef(-1000)
  useEffect(() => { notifyRef.current = onTimeChange }, [onTimeChange])
  const updateTime = useCallback((seconds: number) => {
    setCurrentTime(seconds)
    const milliseconds = Math.round(seconds * 1000)
    if (Math.abs(milliseconds - notifiedMsRef.current) >= 200) {
      notifiedMsRef.current = milliseconds
      notifyRef.current?.(milliseconds)
    }
  }, [])

  useEffect(() => {
    const video = videoRef.current
    setPlaying(false); setCurrentTime(0); setDuration(asset.duration_ms ? asset.duration_ms / 1000 : 0)
    setError(false); setDisplaySize({ width: asset.width, height: asset.height })
    return () => { video?.pause() }
  }, [asset.media_id, asset.duration_ms, asset.width, asset.height])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !('requestVideoFrameCallback' in video)) return
    let handle = 0
    const tick: VideoFrameRequestCallback = (_now, metadata) => {
      updateTime(metadata.mediaTime)
      handle = video.requestVideoFrameCallback(tick)
    }
    handle = video.requestVideoFrameCallback(tick)
    return () => video.cancelVideoFrameCallback(handle)
  }, [asset.media_id, updateTime])

  useEffect(() => {
    if (seekRequest && videoRef.current) {
      videoRef.current.currentTime = seekRequest.ms / 1000
      updateTime(seekRequest.ms / 1000)
    }
  }, [seekRequest, asset.media_id, updateTime])

  async function togglePlay() {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      try { await video.play(); setPlaying(true); setError(false) }
      catch { setError(true) }
    } else { video.pause(); setPlaying(false) }
  }
  function seek(seconds: number) {
    if (videoRef.current) videoRef.current.currentTime = seconds
    updateTime(seconds)
  }
  function changeVolume(value: number) {
    setVolume(value)
    if (videoRef.current) { videoRef.current.volume = value; videoRef.current.muted = value === 0 }
    setMuted(value === 0)
  }
  function toggleMute() {
    const next = !muted
    setMuted(next)
    if (videoRef.current) videoRef.current.muted = next
  }
  function changeSpeed(value: number) {
    setSpeed(value)
    if (videoRef.current) videoRef.current.playbackRate = value
  }

  return <div className="media-viewer-content" data-testid="video-viewer">
    <div className="video-stage" ref={stageRef}>
      <video ref={videoRef} src={mediaContentUrl(asset.media_id)} poster={asset.thumbnail_available ? mediaThumbnailUrl(asset.media_id) : undefined} preload="metadata" playsInline onTimeUpdate={(event) => updateTime(event.currentTarget.currentTime)} onSeeked={(event) => updateTime(event.currentTarget.currentTime)} onLoadedMetadata={(event) => { setDuration(event.currentTarget.duration); setDisplaySize({ width: event.currentTarget.videoWidth, height: event.currentTarget.videoHeight }) }} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => setError(true)} aria-label={asset.original_filename} />
      <div className="video-overlay-region" style={{ width: overlayWidth, height: overlayHeight }}>
        <OverlayCanvas width={overlayWidth} height={overlayHeight} detections={detections} selectedId={selectedId} showLabels={showLabels} showConfidence={showConfidence} />
      </div>
      {showCaptions && caption && validGeometry && <div className="video-caption-overlay">{caption.edited_text ?? caption.text}<small>{(caption.timestamp_ms / 1000).toFixed(2)}s · {caption.source}</small></div>}
      {!validGeometry && <p className="media-load-error" role="alert">Video display dimensions differ from the analyzed source. Overlays are hidden.</p>}
      {!playing && !error && <Button type="button" className="video-center-play" onClick={() => void togglePlay()} aria-label="Play video"><Play size={21} fill="currentColor" /></Button>}
      {error && <p className="media-load-error" role="alert">This video could not be played by the browser. Check its codec or try another file.</p>}
    </div>
    <div className="video-controls">
      <MediaTimeline currentTime={currentTime} duration={duration} onSeek={seek} markers={markers} />
      {markers.length > 0 && <div className="timeline-legend"><span>● Objects</span><span>● Tracks</span><span>● Captions</span><span>● Q&A frames</span><span>● Sampled coverage</span>{markers.some(marker => marker.kind === 'failure') && <span>● Interrupted/failed</span>}</div>}
      <div className="video-control-row">
        <Button type="button" variant="ghost" size="icon" onClick={() => void togglePlay()} aria-label={playing ? 'Pause video' : 'Play video'}>{playing ? <Pause size={17} /> : <Play size={17} />}</Button>
        <Button type="button" variant="ghost" size="icon" onClick={toggleMute} aria-label={muted ? 'Unmute video' : 'Mute video'}>{muted ? <VolumeX size={17} /> : <Volume2 size={17} />}</Button>
        <input className="volume-slider" type="range" min={0} max={1} step={0.05} value={muted ? 0 : volume} onChange={(event) => changeVolume(Number(event.target.value))} aria-label="Video volume" />
        <span className="video-controls-spacer" />
        <label className="speed-label">Speed <select value={speed} onChange={(event) => changeSpeed(Number(event.target.value))} aria-label="Playback speed"><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={1.5}>1.5×</option><option value={2}>2×</option></select></label>
        <Button type="button" variant="ghost" size="icon" onClick={() => void stageRef.current?.requestFullscreen?.()} aria-label="Fullscreen video"><Maximize2 size={16} /></Button>
      </div>
    </div>
  </div>
}
