import type { AnalysisRecord, DetectedObject } from './vision'

export interface LiveStarted {
  type: 'session.started'; protocol_version: 1; session_id: string
  active_sessions: number; max_width: number; max_height: number
  max_frame_bytes: number; max_in_flight_frames: number; max_fps: number
}
export interface LiveResult {
  type: 'frame.result'; protocol_version: 1; session_id: string; frame_id: string
  captured_at_ms: number; source_width: number; source_height: number
  detections: DetectedObject[]; model: NonNullable<AnalysisRecord['model']>
  inference_ms: number; processing_ms: number; result_at: string
  outcome: 'processed'
}
export type LiveMessage = LiveStarted | LiveResult | {
  type: 'frame.skipped'; session_id: string; frame_id: string; reason: string
} | { type: 'session.error'; session_id: string; code: string; message: string } | {
  type: 'session.stopped'; session_id: string; processed_frames: number; skipped_frames: number
}
