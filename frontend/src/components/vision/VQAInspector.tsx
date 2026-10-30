import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { askImage, deleteConversation, getVisionProviders, listConversations } from '@/lib/multimodal'
import { mediaErrorMessage } from '@/lib/media'
import { useExternalConsent } from './useExternalConsent'
import type { VQAConversation } from '@/types/multimodal'

export function VQAInspector({ mediaId, isVideo }: { mediaId: string | null; isVideo: boolean }) {
  const queryClient = useQueryClient()
  const [question, setQuestion] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { consent, setConsent } = useExternalConsent(mediaId)
  const providers = useQuery({ queryKey: ['vision-providers'], queryFn: getVisionProviders,
    refetchInterval: 15000 })
  const conversations = useQuery({ queryKey: ['vqa-conversations', mediaId],
    queryFn: () => listConversations(mediaId!), enabled: !!mediaId && !isVideo })
  const items = conversations.data ?? []
  const selected = selectedId === 'new' ? null :
    items.find(item => item.conversation_id === selectedId) ?? items[0] ?? null
  const ask = useMutation({ mutationFn: () => askImage(mediaId!, question.trim(), selected?.conversation_id ?? null, consent),
    onSuccess: (record: VQAConversation) => {
      queryClient.setQueryData<VQAConversation[]>(['vqa-conversations', mediaId], old =>
        [record, ...(old ?? []).filter(item => item.conversation_id !== record.conversation_id)])
      setSelectedId(record.conversation_id); setQuestion('')
      void queryClient.invalidateQueries({ queryKey: ['vision-providers'] })
      void queryClient.invalidateQueries({ queryKey: ['capabilities'] })
    } })
  const remove = useMutation({ mutationFn: () => deleteConversation(mediaId!, selected!.conversation_id),
    onSuccess: () => { setSelectedId(null); void queryClient.invalidateQueries({ queryKey: ['vqa-conversations', mediaId] }) } })
  const state = providers.data?.vqa.state ?? 'checking'
  return <section className="multimodal-inspector" aria-label="Visual questions">
    <div className="section-label">IMAGE QUESTIONS</div>
    {!mediaId ? <p className="analysis-message">Select or upload an image to ask a question.</p> :
      isVideo ? <p className="analysis-message">Video frame questions are planned for Phase 6.</p> : <>
        <p className="analysis-hint">OpenAI vision: {state}. {state === 'unconfigured' ? 'Set OPENAI_API_KEY on the backend to enable Q&A.' : 'Answers are model assessments of the selected image.'}</p>
        <label className="external-consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /> Allow this image to be sent to OpenAI for questions and descriptions.</label>
        <div className="multimodal-actions"><button type="button" onClick={() => setSelectedId('new')}>New conversation</button>
          {selected && <button type="button" disabled={remove.isPending} onClick={() => remove.mutate()}>Clear conversation</button>}</div>
        {items.length > 0 && <label className="multimodal-field">Saved conversations<select aria-label="Saved conversation" value={selected?.conversation_id ?? 'new'} onChange={event => setSelectedId(event.target.value)}><option value="new">New conversation</option>{items.map(item => <option key={item.conversation_id} value={item.conversation_id}>{new Date(item.updated_at).toLocaleString()} · {item.messages.find(message => message.role === 'user')?.text.slice(0, 32)}</option>)}</select></label>}
        <div className="vqa-messages" aria-live="polite">{selected && selectedId !== 'new' ? selected.messages.map(message => <article key={message.message_id} className={`vqa-message vqa-${message.role}`}><strong>{message.role === 'user' ? 'You' : 'Vision AI'}</strong><p>{message.text}</p>{message.role === 'assistant' && <small>Grounding: {message.grounding_status?.replace('_', ' ')} · {message.model} · {message.duration_ms?.toFixed(0)} ms{message.usage ? ` · ${message.usage.total_tokens} tokens` : ''}{message.uncertainty_note ? ` · ${message.uncertainty_note}` : ''}</small>}</article>) : <p className="analysis-message">Start a new image conversation.</p>}</div>
        <form onSubmit={event => { event.preventDefault(); if (question.trim()) ask.mutate() }}><label className="multimodal-field">Question<textarea aria-label="Question about image" value={question} maxLength={1000} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); if (question.trim() && consent && state !== 'unconfigured' && !ask.isPending) ask.mutate() } }} placeholder="What is visible in this image?" /></label><button type="submit" disabled={!question.trim() || !consent || state === 'unconfigured' || ask.isPending}>{ask.isPending ? 'Asking…' : 'Ask image'}</button></form>
        {ask.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(ask.error)}</p>}
        {remove.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(remove.error)}</p>}
        {conversations.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(conversations.error)}</p>}
      </>}
  </section>
}
