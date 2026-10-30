export type MediaType = 'image' | 'video'
export type PlaybackCompatibility = 'likely' | 'uncertain'

export interface MediaAsset {
  media_id: string
  original_filename: string
  media_type: MediaType
  detected_mime_type: string
  width: number
  height: number
  file_size_bytes: number
  duration_ms: number | null
  frame_rate: number | null
  video_codec: string | null
  playback_compatibility: PlaybackCompatibility | null
  created_at: string
  sha256: string
  thumbnail_available: boolean
}

export interface ApiError { error: { code: string; message: string } }
export interface MediaLimits {
  max_image_bytes: number
  max_video_bytes: number
  max_video_duration_ms: number
  max_image_pixels: number
}
export interface NormalizedBoundingBox { x1: number; y1: number; x2: number; y2: number }
export interface DetectionOverlay {
  id?: string
  classId?: number
  box: NormalizedBoundingBox
  label: string
  confidence: number
  trackingId?: string
}
export interface RegionOverlay { id: string; box: NormalizedBoundingBox; label?: string }
export interface CaptionOverlay { text: string; box?: NormalizedBoundingBox }
export interface TimestampedAnalysisResult {
  timestampMs: number
  detections?: DetectionOverlay[]
  regions?: RegionOverlay[]
  captions?: CaptionOverlay[]
}

