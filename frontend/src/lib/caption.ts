import { api } from '@/lib/api'
import type { CaptionMode, CaptionModelStatus, CaptionRecord } from '@/types/caption'

const mediaPath = (id: string) => `/api/v1/media/${encodeURIComponent(id)}`
export async function listCaptions(id: string): Promise<CaptionRecord[]> {
  return (await api.get<CaptionRecord[]>(`${mediaPath(id)}/captions`)).data
}
export async function getCaptionModel(): Promise<CaptionModelStatus> {
  return (await api.get<CaptionModelStatus>('/api/v1/vision/caption-model')).data
}
export async function generateCaption(id: string, mode: CaptionMode): Promise<CaptionRecord> {
  return (await api.post<CaptionRecord>(`${mediaPath(id)}/caption`, { mode }, { timeout: 0 })).data
}
export async function generateDenseRegions(id: string): Promise<CaptionRecord> {
  return (await api.post<CaptionRecord>(`${mediaPath(id)}/dense-regions`, {}, { timeout: 0 })).data
}
export async function describeObject(id: string, detectionAnalysisId: string, detectionId: string): Promise<CaptionRecord> {
  return (await api.post<CaptionRecord>(`${mediaPath(id)}/regions/describe`, {
    detection_analysis_id: detectionAnalysisId, detection_id: detectionId,
  }, { timeout: 0 })).data
}
