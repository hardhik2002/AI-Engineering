import type { BoundingBox } from '@/types/vision'

export type CaptionMode = 'short' | 'detailed' | 'extended'
export type CaptionTask = CaptionMode | 'dense' | 'selected_object'
export interface CaptionModel { provider: string; checkpoint: string; revision: string; device: string; package_version: string }
export interface CaptionRegion { id: string; description: string; bounding_box: BoundingBox; model: CaptionModel }
export interface CaptionRecord {
  analysis_id: string
  media_id: string
  task: CaptionTask
  status: 'completed'
  created_at: string
  completed_at: string
  model: CaptionModel
  duration_ms: number
  model_load_ms: number
  inference_ms: number
  text: string | null
  regions: CaptionRegion[]
  detection_analysis_id: string | null
  detection_id: string | null
}
export interface CaptionModelStatus { state: 'not_installed' | 'installed_not_loaded' | 'loading' | 'ready' | 'error'; name: string; revision: string; device: string | null }
