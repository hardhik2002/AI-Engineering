import { useEffect, useRef, useState, type PointerEvent, type WheelEvent } from 'react'
import { Maximize2, Minus, Plus, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { OverlayCanvas } from '@/components/media/OverlayCanvas'
import { useElementSize } from '@/components/media/useElementSize'
import { mediaContentUrl } from '@/lib/media'
import type { DetectionOverlay, MediaAsset, RegionOverlay } from '@/types/media'

interface Props { asset: MediaAsset; detections?: DetectionOverlay[]; regions?: RegionOverlay[]; selectedId?: string | null; onSelect?: (id: string | null) => void; showLabels?: boolean; showConfidence?: boolean }
const percentPosition = (value: number) => `${Number((value * 100).toFixed(4))}%`

export function ImageViewer({ asset, detections = [], regions = [], selectedId, onSelect, showLabels = true, showConfidence = true }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null)
  const viewport = useElementSize(viewportRef)
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [error, setError] = useState(false)
  const fit = Math.min(1, (viewport.width - 32) / asset.width, (viewport.height - 32) / asset.height)
  const width = Math.max(1, Math.round(asset.width * fit))
  const height = Math.max(1, Math.round(asset.height * fit))

  useEffect(() => { setZoom(1); setOffset({ x: 0, y: 0 }); setError(false) }, [asset.media_id])

  function reset() { setZoom(1); setOffset({ x: 0, y: 0 }) }
  function adjustZoom(delta: number) {
    setZoom((current) => {
      const next = Math.min(5, Math.max(1, Math.round((current + delta) * 10) / 10))
      if (next === 1) setOffset({ x: 0, y: 0 })
      return next
    })
  }
  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    if (zoom <= 1) return
    drag.current = { x: event.clientX, y: event.clientY, originX: offset.x, originY: offset.y }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return
    setOffset({ x: drag.current.originX + event.clientX - drag.current.x,
      y: drag.current.originY + event.clientY - drag.current.y })
  }
  function pointerUp(event: PointerEvent<HTMLDivElement>) {
    drag.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }
  function wheel(event: WheelEvent<HTMLDivElement>) {
    if (event.ctrlKey) return
    event.preventDefault()
    adjustZoom(event.deltaY < 0 ? 0.2 : -0.2)
  }

  async function fullscreen() {
    if (!viewportRef.current) return
    if (document.fullscreenElement) await document.exitFullscreen()
    else await viewportRef.current.requestFullscreen()
  }

  return <div className="media-viewer-content" data-testid="image-viewer">
    <div className="image-controls" aria-label="Image view controls">
      <Button type="button" variant="ghost" size="small" onClick={reset}><Maximize2 size={14} />Fit screen</Button>
      <span className="control-divider" />
      <Button type="button" variant="ghost" size="icon" onClick={() => adjustZoom(-0.25)} disabled={zoom <= 1} aria-label="Zoom out"><Minus size={16} /></Button>
      <span className="zoom-level">{Math.round(zoom * 100)}%</span>
      <Button type="button" variant="ghost" size="icon" onClick={() => adjustZoom(0.25)} disabled={zoom >= 5} aria-label="Zoom in"><Plus size={16} /></Button>
      <Button type="button" variant="ghost" size="icon" onClick={reset} aria-label="Reset zoom" title="Reset zoom"><RotateCcw size={15} /></Button>
      <Button type="button" variant="ghost" size="small" onClick={() => void fullscreen()} aria-label="Toggle image fullscreen">Fullscreen</Button>
    </div>
    <div ref={viewportRef} className={`image-viewport ${zoom > 1 ? 'pannable' : ''}`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp} onWheel={wheel} onClick={(event) => { if (event.target === event.currentTarget) onSelect?.(null) }}>
      {error ? <p className="media-load-error" role="alert">Image could not be loaded from the backend.</p> :
        <div className="image-layer" style={{ width, height, transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px)) scale(${zoom})` }}>
          <img src={mediaContentUrl(asset.media_id)} alt={asset.original_filename} width={width} height={height} draggable={false} onError={() => setError(true)} />
          <OverlayCanvas width={width} height={height} detections={detections} regions={regions} selectedId={selectedId} showLabels={showLabels} showConfidence={showConfidence} />
          {detections.filter((item) => item.id).map((item) => <button key={item.id} type="button" className="detection-hit" style={{ left: percentPosition(item.box.x1), top: percentPosition(item.box.y1), width: percentPosition(item.box.x2 - item.box.x1), height: percentPosition(item.box.y2 - item.box.y1) }} aria-label={`Select ${item.label} ${Math.round(item.confidence * 100)} percent`} aria-pressed={selectedId === item.id} onClick={() => onSelect?.(item.id ?? null)} />)}
        </div>}
    </div>
  </div>
}
