import { useEffect, useRef, useState, type PointerEvent, type WheelEvent } from 'react'
import { Maximize2, Minus, Plus, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { OverlayCanvas } from '@/components/media/OverlayCanvas'
import { useElementSize } from '@/components/media/useElementSize'
import { mediaContentUrl } from '@/lib/media'
import type { DetectionOverlay, MediaAsset, RegionOverlay } from '@/types/media'

interface Props { asset: MediaAsset; detections?: DetectionOverlay[]; regions?: RegionOverlay[] }

export function ImageViewer({ asset, detections = [], regions = [] }: Props) {
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

  return <div className="media-viewer-content" data-testid="image-viewer">
    <div className="image-controls" aria-label="Image view controls">
      <Button type="button" variant="ghost" size="small" onClick={reset}><Maximize2 size={14} />Fit screen</Button>
      <span className="control-divider" />
      <Button type="button" variant="ghost" size="icon" onClick={() => adjustZoom(-0.25)} disabled={zoom <= 1} aria-label="Zoom out"><Minus size={16} /></Button>
      <span className="zoom-level">{Math.round(zoom * 100)}%</span>
      <Button type="button" variant="ghost" size="icon" onClick={() => adjustZoom(0.25)} disabled={zoom >= 5} aria-label="Zoom in"><Plus size={16} /></Button>
      <Button type="button" variant="ghost" size="icon" onClick={reset} aria-label="Reset zoom" title="Reset zoom"><RotateCcw size={15} /></Button>
    </div>
    <div ref={viewportRef} className={`image-viewport ${zoom > 1 ? 'pannable' : ''}`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp} onWheel={wheel}>
      {error ? <p className="media-load-error" role="alert">Image could not be loaded from the backend.</p> :
        <div className="image-layer" style={{ width, height, transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px)) scale(${zoom})` }}>
          <img src={mediaContentUrl(asset.media_id)} alt={asset.original_filename} width={width} height={height} draggable={false} onError={() => setError(true)} />
          <OverlayCanvas width={width} height={height} detections={detections} regions={regions} />
        </div>}
    </div>
  </div>
}
