import type { AnalysisRecord } from '@/types/vision'
import type { VQAConversation } from '@/types/multimodal'
import type { TokenUsage } from '@/types/multimodal'

export type VideoJobState = 'queued' | 'running' | 'completed' | 'failed' | 'cancel_requested' | 'cancelled' | 'interrupted'
export interface VideoParameters {
  detection_fps: number; caption_interval_seconds: number
  generate_captions: boolean; track_objects: boolean
  detection: { confidence: number; iou: number; image_size: number; max_detections: number }
}
export interface VideoAnalysis {
  analysis_id: string; media_id: string; job_id: string; parameters: VideoParameters
  status: VideoJobState; created_at: string; completed_at: string | null
  duration_ms: number; coverage_end_ms: number; processed_frames: number
  caption_frames: number; elapsed_ms: number; error_code: string | null
}
export interface VideoJob {
  job_id: string; analysis_id: string; media_id: string; kind: 'analysis' | 'caption_frame'
  status: VideoJobState; stage: string; processed_frames: number
  total_frames_estimate: number | null; current_timestamp_ms: number | null
  elapsed_ms: number; error_code: string | null; created_at: string
  updated_at: string; revision: number; target_timestamp_ms: number | null
}
export interface VideoDetection {
  id: string; class_id: number; label: string; confidence: number
  bounding_box: { x: number; y: number; width: number; height: number }
  track_id: number | null
}
export interface VideoFrameResult {
  frame_id: string; analysis_id: string; timestamp_ms: number
  source_pts: number; time_base: string; source_width: number; source_height: number
  detections: VideoDetection[]; model: NonNullable<AnalysisRecord['model']>; inference_ms: number
}
export interface VideoCaption {
  caption_id: string; analysis_id: string; frame_id: string | null
  timestamp_ms: number; text: string; edited_text: string | null
  source: 'florence' | 'openai'; model: string | { checkpoint: string; device: string; revision: string; package_version: string }
  inference_ms: number; usage?: TokenUsage | null; created_at: string; version: number
}
export interface VideoTrack {
  track_id: number; class_id: number; label: string
  first_timestamp_ms: number; last_timestamp_ms: number; sampled_observations: number
}
export interface VideoTimelineMarker { timestamp_ms: number; object_count: number; track_ids: number[] }
export interface VideoVQAResponse { conversation: VQAConversation; examined_timestamps_ms: number[] }
