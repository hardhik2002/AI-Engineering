import { useEffect, useRef } from 'react'
import type { DetectionOverlay, RegionOverlay } from '@/types/media'

interface Props {
  width: number
  height: number
  detections?: DetectionOverlay[]
  regions?: RegionOverlay[]
  className?: string
}

export function OverlayCanvas({ width, height, detections = [], regions = [], className = '' }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || width <= 0 || height <= 0) return
    const ratio = window.devicePixelRatio || 1
    canvas.width = Math.round(width * ratio)
    canvas.height = Math.round(height * ratio)
    const context = canvas.getContext('2d')
    if (!context) return
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    context.clearRect(0, 0, width, height)
    for (const region of regions) {
      context.strokeStyle = '#d5b6ff'
      context.lineWidth = 2
      context.strokeRect(region.box.x1 * width, region.box.y1 * height,
        (region.box.x2 - region.box.x1) * width, (region.box.y2 - region.box.y1) * height)
    }
    for (const detection of detections) {
      context.strokeStyle = '#7ce6c4'
      context.lineWidth = 2
      context.strokeRect(detection.box.x1 * width, detection.box.y1 * height,
        (detection.box.x2 - detection.box.x1) * width, (detection.box.y2 - detection.box.y1) * height)
    }
  }, [width, height, detections, regions])
  return <canvas ref={canvasRef} className={`overlay-canvas ${className}`} style={{ width, height }} aria-hidden="true" />
}
