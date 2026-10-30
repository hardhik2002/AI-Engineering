import { useEffect, useRef, useState } from 'react'
import { Maximize2, Pause, Play, Volume2, VolumeX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MediaTimeline } from '@/components/media/MediaTimeline'
import { OverlayCanvas } from '@/components/media/OverlayCanvas'
import { useElementSize } from '@/components/media/useElementSize'
import { mediaContentUrl, mediaThumbnailUrl } from '@/lib/media'
import type { DetectionOverlay, MediaAsset, RegionOverlay, TimestampedAnalysisResult } from '@/types/media'

interface Props {
  asset: MediaAsset
  detections?: DetectionOverlay[]
  regions?: RegionOverlay[]
  results?: TimestampedAnalysisResult[]
}

export function VideoViewer({ asset, detections = [], regions = [], results = [] }: Props) {
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
  const fit = Math.min(stage.width / asset.width, stage.height / asset.height)
  const overlayWidth = Math.max(0, asset.width * fit)
  const overlayHeight = Math.max(0, asset.height * fit)

  useEffect(() => {
    const video = videoRef.current
    setPlaying(false); setCurrentTime(0); setDuration(asset.duration_ms ? asset.duration_ms / 1000 : 0)
    setError(false)
    return () => { video?.pause() }
  }, [asset.media_id, asset.duration_ms])

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
    setCurrentTime(seconds)
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
      <video ref={videoRef} src={mediaContentUrl(asset.media_id)} poster={asset.thumbnail_available ? mediaThumbnailUrl(asset.media_id) : undefined} preload="metadata" playsInline onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => setError(true)} aria-label={asset.original_filename} />
      <div className="video-overlay-region" style={{ width: overlayWidth, height: overlayHeight }}>
        <OverlayCanvas width={overlayWidth} height={overlayHeight} detections={detections} regions={regions} />
      </div>
      {!playing && !error && <Button type="button" className="video-center-play" onClick={() => void togglePlay()} aria-label="Play video"><Play size={21} fill="currentColor" /></Button>}
      {error && <p className="media-load-error" role="alert">This video could not be played by the browser. Check its codec or try another file.</p>}
    </div>
    <div className="video-controls">
      <MediaTimeline currentTime={currentTime} duration={duration} onSeek={seek} markers={results} />
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
