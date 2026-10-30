export interface BoundingBox { x: number; y: number; width: number; height: number }
export interface DetectedObject {
  id: string
  class_id: number
  label: string
  confidence: number
  bounding_box: BoundingBox
}
export interface DetectionParameters { confidence: number; iou: number; image_size: number; max_detections: number }
export interface AnalysisRecord {
  analysis_id: string
  media_id: string
  status: 'completed' | 'failed'
  task: 'object_detection'
  created_at: string
  completed_at: string
  model: { provider: string; name: string; device: string; version: string; package_version: string } | null
  image: { width: number; height: number; coordinate_space: 'exif_oriented' } | null
  parameters: DetectionParameters
  detections: DetectedObject[]
  summary: { total_objects: number; class_counts: Record<string, number> } | null
  timings_ms: { preprocessing: number; inference: number; postprocessing: number; total: number } | null
  error_code: string | null
}
export interface ModelStatus {
  state: 'not_installed' | 'loading' | 'ready' | 'unavailable' | 'error'
  name: string
  device: string | null
  detail: string | null
}
