import { api } from '@/lib/api'
import type { AccessibilityAnswer, AccessibilityRecord, ImagePurpose, ProviderStatus, VQAConversation } from '@/types/multimodal'

const path = (mediaId: string) => `/api/v1/media/${encodeURIComponent(mediaId)}`
export async function getVisionProviders(): Promise<{ vqa: ProviderStatus; accessibility: ProviderStatus }> {
  return (await api.get('/api/v1/vision/providers')).data
}
export async function listConversations(mediaId: string): Promise<VQAConversation[]> {
  return (await api.get(`${path(mediaId)}/vqa/conversations`)).data
}
export async function askImage(mediaId: string, question: string, conversationId: string | null, consent: boolean): Promise<VQAConversation> {
  return (await api.post(`${path(mediaId)}/vqa`, { question, conversation_id: conversationId, consent_external_transfer: consent }, { timeout: 125000 })).data
}
export async function deleteConversation(mediaId: string, conversationId: string): Promise<void> {
  await api.delete(`${path(mediaId)}/vqa/conversations/${encodeURIComponent(conversationId)}`)
}
export async function listDescriptions(mediaId: string): Promise<AccessibilityRecord[]> {
  return (await api.get(`${path(mediaId)}/accessibility`)).data
}
export async function generateDescription(mediaId: string, body: {
  purpose: ImagePurpose; context: string; audience: string; function: string
  consent_external_transfer: boolean; source_caption_analysis_id?: string
}): Promise<AccessibilityRecord> {
  return (await api.post(`${path(mediaId)}/accessibility`, body, { timeout: 125000 })).data
}
export async function saveDescription(mediaId: string, record: AccessibilityRecord, answer: AccessibilityAnswer): Promise<AccessibilityRecord> {
  return (await api.patch(`${path(mediaId)}/accessibility/${encodeURIComponent(record.result_id)}`, {
    ...answer, expected_version: record.version,
  })).data
}
