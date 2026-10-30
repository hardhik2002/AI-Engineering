export type CapabilityId = 'captioning' | 'vqa' | 'analysis' | 'objects' | 'accessibility' | 'media_upload' | 'image_preview' | 'video_preview'
export type CapabilityStatus = 'planned' | 'available' | 'unavailable'

export interface Capability {
  id: CapabilityId
  name: string
  status: CapabilityStatus
  phase: number
}

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  environment: string
}

export interface MediaDimensions { width: number; height: number }
export interface SourceMedia {
  media_id: string
  kind: 'image' | 'video'
  dimensions: MediaDimensions
  timestamp_ms: number | null
}
export interface NormalizedBox { x1: number; y1: number; x2: number; y2: number }
export interface ModelProvenance { provider: string; model: string; version: string | null }
export interface Detection {
  label: string
  confidence: number
  box: NormalizedBox
  tracking_id: string | null
}

