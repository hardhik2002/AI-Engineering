import { useEffect, useRef } from 'react'
import type { DetectionOverlay, RegionOverlay } from '@/types/media'

interface Props {
  width: number
  height: number
  detections?: DetectionOverlay[]
  regions?: RegionOverlay[]
  className?: string
  selectedId?: string | null
  selectedRegionId?: string | null
  showLabels?: boolean
  showConfidence?: boolean
}

export function OverlayCanvas({ width, height, detections = [], regions = [], className = '', selectedId, selectedRegionId, showLabels = true, showConfidence = true }: Props) {
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
      context.lineWidth = selectedRegionId === region.id ? 4 : 2
      context.strokeRect(region.box.x1 * width, region.box.y1 * height,
        (region.box.x2 - region.box.x1) * width, (region.box.y2 - region.box.y1) * height)
      if (region.label) {
        const x = region.box.x1 * width
        const y = region.box.y1 * height
        context.font = '600 11px sans-serif'
        context.fillStyle = 'rgba(35, 17, 49, .9)'
        context.fillRect(x, y, Math.min(width - x, context.measureText(region.label).width + 10), 19)
        context.fillStyle = '#f2dcff'
        context.fillText(region.label, x + 5, y + 13)
      }
    }
    for (const detection of detections) {
      const hue = ((detection.classId ?? 0) * 47 + 154) % 360
      const color = `hsl(${hue} 85% 65%)`
      const x = detection.box.x1 * width
      const y = detection.box.y1 * height
      const boxWidth = (detection.box.x2 - detection.box.x1) * width
      const boxHeight = (detection.box.y2 - detection.box.y1) * height
      context.strokeStyle = color
      context.lineWidth = selectedId === detection.id ? 4 : 2
      context.strokeRect(x, y, boxWidth, boxHeight)
      const caption = [showLabels ? detection.label : '', showConfidence ? `${Math.round(detection.confidence * 100)}%` : ''].filter(Boolean).join(' ')
      if (caption) {
        context.font = '600 11px sans-serif'
        const labelWidth = Math.min(width - x, context.measureText(caption).width + 10)
        const labelY = y >= 21 ? y - 20 : y
        context.fillStyle = 'rgba(4, 10, 15, .88)'
        context.fillRect(x, labelY, labelWidth, 19)
        context.fillStyle = color
        context.fillText(caption, x + 5, labelY + 13)
      }
    }
  }, [width, height, detections, regions, selectedId, selectedRegionId, showLabels, showConfidence])
  return <canvas ref={canvasRef} className={`overlay-canvas ${className}`} style={{ width, height }} aria-hidden="true" />
}
