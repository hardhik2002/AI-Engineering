import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listCaptions } from '@/lib/caption'
import { mediaErrorMessage } from '@/lib/media'
import { generateDescription, getVisionProviders, listDescriptions, saveDescription } from '@/lib/multimodal'
import { useExternalConsent } from './useExternalConsent'
import type { AccessibilityAnswer, AccessibilityRecord, ImagePurpose } from '@/types/multimodal'

const empty: AccessibilityAnswer = { alt_text: '', detailed_description: null, extended_description: null }

export function AccessibilityInspector({ mediaId, isVideo }: { mediaId: string | null; isVideo: boolean }) {
  const queryClient = useQueryClient()
  const [purpose, setPurpose] = useState<ImagePurpose>('informative')
  const [context, setContext] = useState('')
  const [audience, setAudience] = useState('')
  const [imageFunction, setImageFunction] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<AccessibilityAnswer>(empty)
  const [preview, setPreview] = useState(false)
  const [copyNotice, setCopyNotice] = useState('')
  const { consent, setConsent } = useExternalConsent(mediaId)
  const providers = useQuery({ queryKey: ['vision-providers'], queryFn: getVisionProviders,
    refetchInterval: 15000 })
  const descriptions = useQuery({ queryKey: ['accessibility', mediaId], queryFn: () => listDescriptions(mediaId!), enabled: !!mediaId && !isVideo })
  const captions = useQuery({ queryKey: ['captions', mediaId], queryFn: () => listCaptions(mediaId!), enabled: !!mediaId && !isVideo })
  const records = descriptions.data ?? []
  const selected = records.find(item => item.result_id === selectedId) ?? records[0] ?? null
  useEffect(() => { setDraft(selected?.edited ?? selected?.generated ?? empty) }, [selected])
  const onSaved = (record: AccessibilityRecord) => {
    queryClient.setQueryData<AccessibilityRecord[]>(['accessibility', mediaId], old =>
      [record, ...(old ?? []).filter(item => item.result_id !== record.result_id)])
    setSelectedId(record.result_id); setDraft(record.edited ?? record.generated)
  }
  const generate = useMutation({ mutationFn: (captionId?: string) => generateDescription(mediaId!, {
    purpose, context, audience, function: imageFunction,
    consent_external_transfer: consent, source_caption_analysis_id: captionId,
  }), onSuccess: onSaved })
  const save = useMutation({ mutationFn: () => saveDescription(mediaId!, selected!, draft), onSuccess: onSaved })
  const state = providers.data?.accessibility.state ?? 'checking'
  const suggestions = (captions.data ?? []).filter(item => item.text && item.task !== 'selected_object')
  const copy = async () => {
    try { await navigator.clipboard.writeText(draft.alt_text); setCopyNotice('Alt text copied.') }
    catch { setCopyNotice('Clipboard unavailable. Select and copy the alt text manually.') }
  }
  return <section className="multimodal-inspector" aria-label="Accessible descriptions">
    <div className="section-label">ACCESSIBLE DESCRIPTION</div>
    {!mediaId ? <p className="analysis-message">Select or upload an image to write a description.</p> :
      isVideo ? <p className="analysis-message">Video descriptions are planned for Phase 6.</p> : <>
        <p className="analysis-hint">OpenAI vision: {state}. Decorative alt text is local. Saved Florence captions can be used as editable suggestions.</p>
        <label className="external-consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /> Allow this image to be sent to OpenAI for questions and descriptions.</label>
        <label className="multimodal-field">Image purpose<select value={purpose} onChange={event => setPurpose(event.target.value as ImagePurpose)}><option value="informative">Informative</option><option value="decorative">Decorative (empty alt text)</option><option value="functional">Functional</option><option value="complex">Complex</option></select></label>
        <label className="multimodal-field">Usage context<input value={context} maxLength={1000} onChange={event => setContext(event.target.value)} placeholder="Where will this image appear?" /></label>
        <label className="multimodal-field">Audience<input value={audience} maxLength={300} onChange={event => setAudience(event.target.value)} /></label>
        {purpose === 'functional' && <label className="multimodal-field">Linked action<input value={imageFunction} maxLength={300} onChange={event => setImageFunction(event.target.value)} placeholder="What does activating it do?" /></label>}
        <div className="multimodal-actions"><button type="button" disabled={generate.isPending || (purpose !== 'decorative' && (!consent || state === 'unconfigured'))} onClick={() => generate.mutate(undefined)}>{generate.isPending ? 'Generating…' : purpose === 'decorative' ? 'Create empty alt text' : 'Generate with OpenAI'}</button></div>
        {suggestions.length > 0 && <label className="multimodal-field">Use saved Florence caption<select aria-label="Florence suggestion" defaultValue="" onChange={event => { if (event.target.value) generate.mutate(event.target.value) }}><option value="">Choose a saved caption</option>{suggestions.map(item => <option key={item.analysis_id} value={item.analysis_id}>{item.task} · {item.text?.slice(0, 45)}</option>)}</select></label>}
        {records.length > 0 && <label className="multimodal-field">Saved descriptions<select aria-label="Saved description" value={selected?.result_id ?? ''} onChange={event => setSelectedId(event.target.value)}>{records.map(item => <option key={item.result_id} value={item.result_id}>{new Date(item.created_at).toLocaleString()} · {item.purpose} · {item.source}</option>)}</select></label>}
        {selected && <div className="description-editor"><p className="analysis-hint">Source: {selected.source.replace('_', ' ')}{selected.model ? ` · ${selected.model}` : ''}{selected.usage ? ` · ${selected.usage.total_tokens} tokens` : ''}. Review and edit before use.</p>
          <label className="multimodal-field">Alt text<textarea aria-label="Alt text" value={draft.alt_text} maxLength={1000} onChange={event => setDraft({ ...draft, alt_text: event.target.value })} /></label>
          <label className="multimodal-field">Detailed description<textarea aria-label="Detailed description" value={draft.detailed_description ?? ''} maxLength={5000} onChange={event => setDraft({ ...draft, detailed_description: event.target.value || null })} /></label>
          <label className="multimodal-field">Extended description<textarea aria-label="Extended description" value={draft.extended_description ?? ''} maxLength={8000} onChange={event => setDraft({ ...draft, extended_description: event.target.value || null })} /></label>
          <div className="multimodal-actions"><button type="button" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save edit'}</button><button type="button" onClick={() => void copy()}>Copy alt text</button><button type="button" onClick={() => setPreview(!preview)}>{preview ? 'Hide preview' : 'Screen reader preview'}</button></div>
          {copyNotice && <p role="status" className="analysis-hint">{copyNotice}</p>}
          {preview && <div className="analysis-message" role="status">Image description: {draft.alt_text || '(decorative image, no announcement)'}</div>}
          {save.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(save.error)}</p>}
        </div>}
        {generate.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(generate.error)}</p>}
        {descriptions.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(descriptions.error)}</p>}
      </>}
  </section>
}
