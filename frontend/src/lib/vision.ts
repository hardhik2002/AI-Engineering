import { api } from '@/lib/api'
import type { AnalysisRecord, DetectionParameters, ModelStatus } from '@/types/vision'

export async function listAnalyses(mediaId: string): Promise<AnalysisRecord[]> {
  const { data } = await api.get<AnalysisRecord[]>(`/api/v1/media/${encodeURIComponent(mediaId)}/analyses`)
  return data
}

export async function analyzeImage(mediaId: string, parameters: DetectionParameters): Promise<AnalysisRecord> {
  const { data } = await api.post<AnalysisRecord>(`/api/v1/media/${encodeURIComponent(mediaId)}/analyze`, {
    tasks: ['object_detection'], parameters,
  }, { timeout: 120_000 })
  return data
}

export async function getModels(): Promise<ModelStatus[]> {
  const { data } = await api.get<ModelStatus[]>('/api/v1/vision/models')
  return data
}
