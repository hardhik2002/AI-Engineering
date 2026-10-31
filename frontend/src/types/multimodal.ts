export type ImagePurpose = 'informative' | 'decorative' | 'functional' | 'complex'
export interface TokenUsage { input_tokens: number; output_tokens: number; total_tokens: number }
export interface ProviderStatus { provider: string; state: 'unconfigured' | 'configured' | 'available' | 'unavailable' | 'error'; model: string }
export interface VQAMessage {
  message_id: string; role: 'user' | 'assistant'; text: string; created_at: string
  grounding_status: 'supported' | 'uncertain' | 'insufficient_evidence' | null
  uncertainty_note: string | null; provider: string | null; model: string | null
  duration_ms: number | null; usage: TokenUsage | null
  frame_timestamps_ms?: number[] | null
}
export interface VQAConversation {
  conversation_id: string; media_id: string; created_at: string; updated_at: string
  messages: VQAMessage[]
}
export interface AccessibilityAnswer {
  alt_text: string; detailed_description: string | null; extended_description: string | null
}
export interface AccessibilityRecord {
  result_id: string; media_id: string; purpose: ImagePurpose; context: string
  audience: string; function: string; source: 'openai' | 'decorative_local' | 'florence_suggestion'
  generated: AccessibilityAnswer; edited: AccessibilityAnswer | null
  model: string | null; provider: string | null; duration_ms: number | null
  usage: TokenUsage | null; version: number; created_at: string; updated_at: string
}
