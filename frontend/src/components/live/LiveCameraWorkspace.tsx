import { useRef, useState } from 'react'
import { Camera, CameraOff, Download, Maximize2 } from 'lucide-react'
import { OverlayCanvas } from '@/components/media/OverlayCanvas'
import { useElementSize } from '@/components/media/useElementSize'
import type { MediaAsset } from '@/types/media'
import type { LiveCameraController } from './useLiveCamera'

function number(value: number | null, unit = '') {
  return value === null || !Number.isFinite(value) ? '—' : `${value.toFixed(1)}${unit}`
}

export function LiveCameraStage({ camera, onSnapshot }: {
  camera: LiveCameraController; onSnapshot: (asset: MediaAsset) => void
}) {
  const [dimensions, setDimensions] = useState({ width: 640, height: 480 })
  const stageRef = useRef<HTMLDivElement>(null)
  const size = useElementSize(stageRef)
  const fit = Math.min(size.width / dimensions.width, size.height / dimensions.height)
  const width = dimensions.width * fit
  const height = dimensions.height * fit
  const aspectMatches = !camera.result || Math.abs(
    camera.result.source_width / camera.result.source_height - dimensions.width / dimensions.height
  ) < 0.02
  const detections = aspectMatches && camera.showBoxes ? (camera.result?.detections ?? [])
    .filter(item => item.confidence >= camera.displayConfidence &&
      !camera.excludedClasses.includes(item.label)) : []
  const overlays = detections.map(item => ({
    id: item.id, classId: item.class_id, label: item.label, confidence: item.confidence,
    box: { x1: item.bounding_box.x, y1: item.bounding_box.y,
      x2: item.bounding_box.x + item.bounding_box.width,
      y2: item.bounding_box.y + item.bounding_box.height },
  }))
  return <section className="live-workspace" aria-label="Live Camera workspace">
    <div className="live-controls">
      {camera.status === 'running' || camera.status === 'connecting' || camera.status === 'requesting' ?
        <button type="button" className="video-action" onClick={camera.stop}><CameraOff size={16} /> Stop Camera</button> :
        <button type="button" className="video-action" onClick={() => void camera.start()}><Camera size={16} /> Start Camera</button>}
      <button type="button" disabled={camera.status !== 'running' || camera.saving} onClick={() => void camera.snapshot(onSnapshot)}><Download size={15} /> {camera.saving ? 'Saving…' : 'Capture Snapshot'}</button>
      <span className={`live-status live-${camera.status}`} role="status">{camera.status.replace('_', ' ')}</span>
    </div>
    <div className="live-settings">
      {camera.devices.length > 0 && <label>Camera <select aria-label="Camera device" value={camera.deviceId} onChange={event => camera.setDeviceId(event.target.value)}><option value="">Default camera</option>{camera.devices.map(device => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${device.deviceId.slice(0, 5)}`}</option>)}</select></label>}
      <label>Facing <select aria-label="Camera facing" value={camera.facingMode} onChange={event => { camera.setDeviceId(''); camera.setFacingMode(event.target.value as 'user' | 'environment') }}><option value="user">Front</option><option value="environment">Back</option></select></label>
      <label>Resolution <select aria-label="Camera resolution" value={camera.resolution} onChange={event => camera.setResolution(event.target.value as '320x240' | '640x480')}><option value="320x240">320 × 240</option><option value="640x480">640 × 480</option></select></label>
      <label>Analysis rate <select aria-label="Live analysis FPS" value={camera.analysisFps} onChange={event => camera.setAnalysisFps(Number(event.target.value))}><option value={0.5}>0.5 FPS</option><option value={1}>1 FPS</option><option value={2}>2 FPS</option></select></label>
      <label className="analysis-checks"><input type="checkbox" checked={camera.mirror} onChange={event => camera.setMirror(event.target.checked)} /> Mirror preview</label>
    </div>
    {camera.error && <p className="analysis-message analysis-error" role="alert">{camera.error}</p>}
    <div className="live-stage" ref={stageRef}>
      <div className="live-image" style={{ width, height, transform: camera.mirror ? 'translate(-50%, -50%) scaleX(-1)' : 'translate(-50%, -50%)' }}>
        <video ref={camera.videoRef} autoPlay muted playsInline aria-label="Live camera preview" onLoadedMetadata={event => setDimensions({ width: event.currentTarget.videoWidth || 640, height: event.currentTarget.videoHeight || 480 })} />
        <OverlayCanvas width={width} height={height} detections={overlays} selectedId={camera.selectedId} showLabels={camera.showLabels} showConfidence={camera.showConfidence} />
        {detections.map(item => <button key={item.id} type="button" className="live-object-hit" style={{ left: `${item.bounding_box.x * 100}%`, top: `${item.bounding_box.y * 100}%`, width: `${item.bounding_box.width * 100}%`, height: `${item.bounding_box.height * 100}%` }} aria-label={`Select live ${item.label} ${Math.round(item.confidence * 100)} percent`} onClick={() => camera.setSelectedId(item.id)} />)}
      </div>
      {camera.status === 'stopped' && <div className="live-placeholder"><Camera size={30} /><strong>Camera is off</strong><span>Start Camera to request browser permission. No frames are saved automatically.</span></div>}
      <button type="button" className="live-fullscreen" onClick={() => { if (!document.fullscreenElement) void stageRef.current?.requestFullscreen?.(); else void document.exitFullscreen?.() }} aria-label="Fullscreen camera"><Maximize2 size={17} /></button>
    </div>
    <div className="live-metrics" aria-label="Live processing metrics">
      <span>Preview {number(camera.metrics.previewFps, ' FPS')}</span>
      <span>AI {number(camera.metrics.inferenceFps, ' FPS')}</span>
      <span>Captured {camera.metrics.captured}</span><span>Sent {camera.metrics.sent}</span>
      <span>Processed {camera.metrics.processed}</span><span>Skipped {camera.metrics.dropped}</span>
      <span>Inference {number(camera.metrics.inferenceMs, ' ms')}</span>
      <span>Round trip {number(camera.metrics.roundTripMs, ' ms')}</span>
      <span>Sessions {camera.activeSessions}</span>
    </div>
    <p className="analysis-hint">Boxes describe the most recently analyzed frame. The live preview continues between analyses; stale boxes clear automatically.</p>
  </section>
}

export function LiveCameraInspector({ camera }: { camera: LiveCameraController }) {
  const result = camera.result
  const classes = [...new Set((result?.detections ?? []).map(item => item.label))]
  const visible = (result?.detections ?? []).filter(item => item.confidence >= camera.displayConfidence &&
    !camera.excludedClasses.includes(item.label))
  const selected = visible.find(item => item.id === camera.selectedId)
  return <section className="multimodal-inspector" aria-label="Live Camera inspector">
    <div className="section-label">LIVE DETECTIONS</div>
    <p className="analysis-hint">{result ? `${visible.length} objects in latest analyzed frame · ${result.source_width} × ${result.source_height}` : 'No analyzed frame yet.'}</p>
    <label className="analysis-range">Display confidence <span>{camera.displayConfidence.toFixed(2)}</span><input type="range" min="0" max="1" step="0.05" value={camera.displayConfidence} onChange={event => camera.setDisplayConfidence(Number(event.target.value))} aria-label="Live display confidence" /></label>
    <div className="analysis-checks"><label><input type="checkbox" checked={camera.showBoxes} onChange={event => camera.setShowBoxes(event.target.checked)} /> Boxes</label><label><input type="checkbox" checked={camera.showLabels} onChange={event => camera.setShowLabels(event.target.checked)} /> Labels</label><label><input type="checkbox" checked={camera.showConfidence} onChange={event => camera.setShowConfidence(event.target.checked)} /> Scores</label></div>
    {classes.length > 0 && <div className="live-class-filter"><strong>Classes</strong>{classes.map(label => <label key={label}><input type="checkbox" checked={!camera.excludedClasses.includes(label)} onChange={event => camera.setExcludedClasses(event.target.checked ? camera.excludedClasses.filter(value => value !== label) : [...camera.excludedClasses, label])} /> {label}</label>)}</div>}
    <div className="object-list">{visible.map(item => <button key={item.id} type="button" className={camera.selectedId === item.id ? 'selected' : ''} onClick={() => camera.setSelectedId(item.id)}>{item.label} · {Math.round(item.confidence * 100)}%</button>)}{result && visible.length === 0 && <p className="analysis-message">No objects above the display threshold.</p>}</div>
    {selected && <div className="analysis-meta"><strong>Selected: {selected.label}</strong><span>Confidence {selected.confidence.toFixed(3)}</span><span>Box {Object.values(selected.bounding_box).map(value => value.toFixed(3)).join(', ')}</span><button type="button" onClick={() => camera.setSelectedId(null)}>Clear selection</button></div>}
    {result && <p className="analysis-meta">{result.model.name} · {result.model.device} · {result.inference_ms.toFixed(1)} ms<br />Result {new Date(result.result_at).toLocaleTimeString()}</p>}
    <p className="analysis-hint">Live tracking is unavailable in this phase. Detection IDs identify only one analyzed frame.</p>
  </section>
}
