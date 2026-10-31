import { api } from '@/lib/api'
import type { VideoAnalysis, VideoCaption, VideoFrameResult, VideoJob, VideoParameters, VideoTimelineMarker, VideoTrack, VideoVQAResponse } from '@/types/video'

const media = (id: string) => `/api/v1/media/${encodeURIComponent(id)}/video`
const analysis = (id: string) => `/api/v1/video/analyses/${encodeURIComponent(id)}`
export const activeJob = (status: VideoJob['status']) => ['queued', 'running', 'cancel_requested'].includes(status)
export async function startVideoAnalysis(mediaId: string, parameters: VideoParameters): Promise<VideoJob> {
  return (await api.post<VideoJob>(`${media(mediaId)}/analyze`, parameters)).data
}
export async function listVideoAnalyses(mediaId: string): Promise<VideoAnalysis[]> {
  return (await api.get<VideoAnalysis[]>(`${media(mediaId)}/analyses`)).data
}
export async function getVideoJob(jobId: string): Promise<VideoJob> {
  return (await api.get<VideoJob>(`/api/v1/video/jobs/${encodeURIComponent(jobId)}`)).data
}
export async function cancelVideoJob(jobId: string): Promise<VideoJob> {
  return (await api.post<VideoJob>(`/api/v1/video/jobs/${encodeURIComponent(jobId)}/cancel`)).data
}
export async function getVideoFrames(analysisId: string, startMs: number, endMs: number): Promise<VideoFrameResult[]> {
  return (await api.get<VideoFrameResult[]>(`${analysis(analysisId)}/frames`, { params: { start_ms: startMs, end_ms: endMs, limit: 100 } })).data
}
export async function getVideoTimeline(analysisId: string): Promise<VideoTimelineMarker[]> {
  return (await api.get<VideoTimelineMarker[]>(`${analysis(analysisId)}/timeline`)).data
}
export async function getVideoTracks(analysisId: string): Promise<VideoTrack[]> {
  return (await api.get<VideoTrack[]>(`${analysis(analysisId)}/tracks`, { params: { limit: 100 } })).data
}
export async function getVideoCaptions(analysisId: string): Promise<VideoCaption[]> {
  return (await api.get<VideoCaption[]>(`${analysis(analysisId)}/captions`, { params: { limit: 100 } })).data
}
export async function captionVideoFrame(mediaId: string, analysisId: string, timestampMs: number): Promise<VideoJob> {
  return (await api.post<VideoJob>(`${media(mediaId)}/analyses/${encodeURIComponent(analysisId)}/captions`, { timestamp_ms: timestampMs })).data
}
export async function editVideoCaption(analysisId: string, captionId: string, editedText: string, expectedVersion: number): Promise<VideoCaption> {
  return (await api.patch<VideoCaption>(`${analysis(analysisId)}/captions/${encodeURIComponent(captionId)}`, { edited_text: editedText, expected_version: expectedVersion })).data
}
export async function askVideo(mediaId: string, question: string, startMs: number, endMs: number, conversationId: string | null, consent: boolean): Promise<VideoVQAResponse> {
  return (await api.post<VideoVQAResponse>(`${media(mediaId)}/vqa`, { question, start_ms: startMs, end_ms: endMs, conversation_id: conversationId, consent_external_transfer: consent }, { timeout: 125000 })).data
}
export async function refineVideoCaption(mediaId: string, analysisId: string, timestampMs: number, context: string, consent: boolean): Promise<VideoCaption> {
  return (await api.post<VideoCaption>(`${media(mediaId)}/analyses/${encodeURIComponent(analysisId)}/refine`, { timestamp_ms: timestampMs, context, consent_external_transfer: consent }, { timeout: 125000 })).data
}
