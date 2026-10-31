import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteConversation, getVisionProviders, listConversations } from '@/lib/multimodal'
import { mediaErrorMessage } from '@/lib/media'
import { activeJob, askVideo, cancelVideoJob, captionVideoFrame, editVideoCaption, getVideoJob, refineVideoCaption } from '@/lib/video'
import { useExternalConsent } from './useExternalConsent'
import type { VQAConversation } from '@/types/multimodal'
import type { VideoAnalysis, VideoCaption, VideoFrameResult, VideoJob, VideoParameters, VideoTrack } from '@/types/video'

const time = (ms: number) => `${(ms / 1000).toFixed(2)}s`

export function VideoAnalysisControls({ analyses, selected, job, parameters, onParameters,
  onAnalyze, onSelect, loading, error }: {
  analyses: VideoAnalysis[]; selected: VideoAnalysis | null; job: VideoJob | null
  parameters: VideoParameters; onParameters: (value: VideoParameters) => void
  onAnalyze: () => void; onSelect: (id: string) => void; loading: boolean; error: string
}) {
  const cancel = useMutation({ mutationFn: () => cancelVideoJob(job!.job_id) })
  const progress = selected?.duration_ms && job?.current_timestamp_ms != null ?
    Math.min(100, Math.round(job.current_timestamp_ms / selected.duration_ms * 100)) : 0
  return <section className="analysis-run-panel video-analysis-controls" aria-label="Video analysis controls">
    <div><strong>Uploaded video analysis</strong><span>Sampled YOLO26 + ByteTrack + optional Florence captions. CPU processing may take time.</span></div>
    <div className="video-config">
      <label>Detection FPS <input aria-label="Video detection FPS" type="number" min="0.25" max="8" step="0.25" value={parameters.detection_fps} onChange={event => onParameters({ ...parameters, detection_fps: Number(event.target.value) })} /></label>
      <label>Caption interval (s) <input aria-label="Video caption interval" type="number" min="1" max="120" step="1" value={parameters.caption_interval_seconds} onChange={event => onParameters({ ...parameters, caption_interval_seconds: Number(event.target.value) })} /></label>
      <label><input type="checkbox" checked={parameters.track_objects} onChange={event => onParameters({ ...parameters, track_objects: event.target.checked })} /> ByteTrack</label>
      <label><input type="checkbox" checked={parameters.generate_captions} onChange={event => onParameters({ ...parameters, generate_captions: event.target.checked })} /> Florence captions</label>
    </div>
    <button type="button" className="video-action" disabled={loading || parameters.detection_fps < 0.25 || parameters.detection_fps > 8 || parameters.caption_interval_seconds < 1 || parameters.caption_interval_seconds > 120} onClick={onAnalyze}>{loading ? 'Queueing…' : 'Analyze Video'}</button>
    {analyses.length > 0 && <label className="multimodal-field">Saved video analyses<select aria-label="Saved video analysis" value={selected?.analysis_id ?? ''} onChange={event => onSelect(event.target.value)}>{analyses.map(item => <option key={item.analysis_id} value={item.analysis_id}>{new Date(item.created_at).toLocaleString()} · {item.status} · {item.processed_frames} frames</option>)}</select></label>}
    {job && <div className="video-job" role="status"><strong>{job.status.replace('_', ' ')} · {job.stage}</strong><span>{job.processed_frames} sampled frames{job.total_frames_estimate ? ` / ~${job.total_frames_estimate} estimated` : ''} · {time(job.current_timestamp_ms ?? 0)} · {(job.elapsed_ms / 1000).toFixed(1)}s elapsed</span><progress value={progress} max="100" aria-label="Video processing progress" /><small>{progress}% of video timeline reached{selected?.status === 'completed' && selected.coverage_end_ms < selected.duration_ms - 500 ? ' · partial coverage at configured frame limit' : ''}</small>{activeJob(job.status) && <button type="button" onClick={() => cancel.mutate()} disabled={cancel.isPending}>Cancel job</button>}{job.error_code && <small className="analysis-error">{job.error_code}</small>}</div>}
    {error && <p role="alert" className="analysis-message analysis-error">{error}</p>}
    {cancel.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(cancel.error)}</p>}
    <small className="analysis-hint">Results cover only sampled frames. Tracking IDs estimate associations, not distinct physical objects.</small>
  </section>
}

export function VideoDetectionInspector({ analysis, frame, tracks, currentMs, confidence,
  onConfidence, excludedClasses, onExcludedClasses, selectedTrackId, onSelectedTrack,
  showBoxes, onShowBoxes, showLabels, onShowLabels, showConfidence, onShowConfidence,
  onSeek }: {
  analysis: VideoAnalysis | null; frame: VideoFrameResult | null; tracks: VideoTrack[]
  currentMs: number; confidence: number; onConfidence: (value: number) => void
  excludedClasses: string[]; onExcludedClasses: (value: string[]) => void
  selectedTrackId: number | null; onSelectedTrack: (value: number | null) => void
  showBoxes: boolean; onShowBoxes: (value: boolean) => void
  showLabels: boolean; onShowLabels: (value: boolean) => void
  showConfidence: boolean; onShowConfidence: (value: boolean) => void
  onSeek: (ms: number) => void
}) {
  if (!analysis) return <p className="analysis-message">Analyze the uploaded video to inspect sampled objects and tracks.</p>
  const objects = (frame?.detections ?? []).filter(item => item.confidence >= confidence && !excludedClasses.includes(item.label))
  const classes = [...new Set((frame?.detections ?? []).map(item => item.label))]
  return <section className="multimodal-inspector" aria-label="Video objects and tracks">
    <div className="section-label">SAMPLED VIDEO OBJECTS</div>
    <div className="analysis-stats"><div><strong>{analysis.processed_frames}</strong><span>sampled frames</span></div><div><strong>{objects.length}</strong><span>current objects</span></div><div><strong>{tracks.length}{tracks.length === 100 ? '+' : ''}</strong><span>approx. IDs</span></div></div>
    <p className="analysis-hint">Coverage to {time(analysis.coverage_end_ms)} of {time(analysis.duration_ms)}. {frame ? `Showing actual frame ${time(frame.timestamp_ms)} (${frame.source_pts} × ${frame.time_base}).` : `No analyzed frame near ${time(currentMs)}; boxes cleared.`}</p>
    <label className="analysis-range">Display confidence <span>{confidence.toFixed(2)}</span><input aria-label="Video display confidence" type="range" min="0" max="1" step="0.05" value={confidence} onChange={event => onConfidence(Number(event.target.value))} /></label>
    <div className="analysis-checks"><label><input type="checkbox" checked={showBoxes} onChange={event => onShowBoxes(event.target.checked)} /> Boxes</label><label><input type="checkbox" checked={showLabels} onChange={event => onShowLabels(event.target.checked)} /> Labels</label><label><input type="checkbox" checked={showConfidence} onChange={event => onShowConfidence(event.target.checked)} /> Scores</label></div>
    {classes.length > 0 && <div className="analysis-classes">{classes.map(label => <label key={label}><input type="checkbox" checked={!excludedClasses.includes(label)} onChange={event => onExcludedClasses(event.target.checked ? excludedClasses.filter(item => item !== label) : [...excludedClasses, label])} /> {label}</label>)}</div>}
    <div className="section-label">CURRENT FRAME · {frame ? time(frame.timestamp_ms) : 'GAP'}</div>
    <div className="object-list">{objects.map(item => <button key={item.id} type="button" className={selectedTrackId === item.track_id && item.track_id !== null ? 'selected' : ''} onClick={() => onSelectedTrack(item.track_id)}>{item.label}{item.track_id !== null ? ` #${item.track_id}` : ' · untracked'} · {Math.round(item.confidence * 100)}%</button>)}{frame && objects.length === 0 && <p className="analysis-message">No objects above the display threshold on this sampled frame.</p>}</div>
    {tracks.length > 0 && <><div className="section-label">TRACK ASSOCIATIONS</div><div className="object-list">{tracks.map(track => <button key={track.track_id} type="button" className={selectedTrackId === track.track_id ? 'selected' : ''} onClick={() => { onSelectedTrack(track.track_id); onSeek(track.first_timestamp_ms) }}>#{track.track_id} {track.label} · {track.sampled_observations} observations · {time(track.first_timestamp_ms)}–{time(track.last_timestamp_ms)}</button>)}</div></>}
    {frame && <p className="analysis-meta">{frame.model.name} · {frame.model.device} · {frame.inference_ms.toFixed(1)} ms inference · {frame.source_width}×{frame.source_height}</p>}
  </section>
}

export function VideoCaptionInspector({ mediaId, analysis, captions, currentMs, onSeek,
  onRefresh, accessible = false }: {
  mediaId: string; analysis: VideoAnalysis | null; captions: VideoCaption[]
  currentMs: number; onSeek: (ms: number) => void; onRefresh: () => void; accessible?: boolean
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = captions.find(item => item.caption_id === selectedId) ?? captions[0] ?? null
  const [draft, setDraft] = useState('')
  const [context, setContext] = useState('')
  const [notice, setNotice] = useState('')
  const { consent, setConsent } = useExternalConsent(mediaId)
  const providers = useQuery({ queryKey: ['vision-providers'], queryFn: getVisionProviders, enabled: accessible })
  useEffect(() => setDraft(selected?.edited_text ?? selected?.text ?? ''), [selected])
  const [captionJobId, setCaptionJobId] = useState<string | null>(null)
  const captionJob = useQuery({ queryKey: ['video-job', captionJobId], queryFn: () => getVideoJob(captionJobId!), enabled: !!captionJobId, refetchInterval: query => query.state.data && activeJob(query.state.data.status) ? 1000 : false })
  useEffect(() => { if (captionJob.data?.status === 'completed') onRefresh() }, [captionJob.data?.status, onRefresh])
  const create = useMutation({ mutationFn: () => captionVideoFrame(mediaId, analysis!.analysis_id, currentMs), onSuccess: job => setCaptionJobId(job.job_id) })
  const edit = useMutation({ mutationFn: () => editVideoCaption(analysis!.analysis_id, selected!.caption_id, draft, selected!.version), onSuccess: () => onRefresh() })
  const refine = useMutation({ mutationFn: () => refineVideoCaption(mediaId, analysis!.analysis_id, currentMs, context, consent), onSuccess: () => onRefresh() })
  async function copy() { try { await navigator.clipboard.writeText(captions.map(item => `${time(item.timestamp_ms)} ${item.edited_text ?? item.text}`).join('\n')); setNotice('Descriptions copied.') } catch { setNotice('Clipboard unavailable; use Export text.') } }
  function exportText() { const blob = new Blob([captions.map(item => `${time(item.timestamp_ms)} ${item.edited_text ?? item.text}`).join('\n')], { type: 'text/plain' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `visionlab-${analysis?.analysis_id ?? 'video'}-descriptions.txt`; link.click(); URL.revokeObjectURL(link.href) }
  return <section className="multimodal-inspector" aria-label={accessible ? 'Accessible video descriptions' : 'Video captions'}>
    <div className="section-label">{accessible ? 'SCENE DESCRIPTION TIMELINE' : 'TIMESTAMPED CAPTIONS'}</div>
    {!analysis ? <p className="analysis-message">Analyze the video with Florence captions enabled to create a scene timeline.</p> : <>
      <p className="analysis-hint">Descriptions refer to sampled frames only. They do not cover unseen intervals or replace a complete accessible video solution.</p>
      <div className="multimodal-actions"><button type="button" disabled={create.isPending || !['completed', 'interrupted'].includes(analysis.status)} onClick={() => create.mutate()}>{create.isPending ? 'Queueing…' : `Caption frame at ${time(currentMs)}`}</button><button type="button" disabled={!captions.length} onClick={() => void copy()}>Copy timeline</button><button type="button" disabled={!captions.length} onClick={exportText}>Export text</button></div>
      {captionJob.data && <p role="status" className="analysis-message">Frame caption job: {captionJob.data.status}{captionJob.data.error_code ? ` · ${captionJob.data.error_code}` : ''}</p>}
      {captions.length > 0 && <div className="object-list video-caption-list">{captions.map(item => <button key={item.caption_id} type="button" className={selected?.caption_id === item.caption_id ? 'selected' : ''} onClick={() => { setSelectedId(item.caption_id); onSeek(item.timestamp_ms) }}><span>{time(item.timestamp_ms)} · {item.source}</span><span>{item.edited_text ?? item.text}</span></button>)}</div>}
      {captions.length === 0 && <p className="analysis-message">No sampled frame captions saved for this run.</p>}
      {selected && <><p className="analysis-meta">{selected.source} · {typeof selected.model === 'string' ? selected.model : selected.model.checkpoint} · {selected.inference_ms.toFixed(1)} ms{selected.usage ? ` · ${selected.usage.total_tokens} tokens` : ''}</p><label className="multimodal-field">Editable description<textarea aria-label="Editable video description" value={draft} maxLength={8000} onChange={event => setDraft(event.target.value)} /></label><button className="video-action" type="button" disabled={edit.isPending || !draft.trim()} onClick={() => edit.mutate()}>Save description edit</button></>}
      {accessible && <><p className="analysis-hint">OpenAI vision: {providers.data?.accessibility.state ?? 'checking'}.</p><label className="external-consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /> Allow selected video frames to be sent to OpenAI.</label><label className="multimodal-field">Refinement context<input value={context} maxLength={1000} onChange={event => setContext(event.target.value)} /></label><button className="video-action" type="button" disabled={!consent || !['configured', 'available'].includes(providers.data?.accessibility.state ?? '') || refine.isPending} onClick={() => refine.mutate()}>Refine selected frame with OpenAI</button></>}
      {notice && <p role="status" className="analysis-hint">{notice}</p>}
      {(create.isError || edit.isError || refine.isError) && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(create.error ?? edit.error ?? refine.error)}</p>}
    </>}
  </section>
}

export function VideoVQAInspector({ mediaId, currentMs, durationMs, onSeek,
  onRefresh }: { mediaId: string; currentMs: number; durationMs: number
  onSeek: (ms: number) => void; onRefresh: () => void }) {
  const queryClient = useQueryClient()
  const { consent, setConsent } = useExternalConsent(mediaId)
  const [question, setQuestion] = useState('')
  const [startMs, setStartMs] = useState(0)
  const [endMs, setEndMs] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const providers = useQuery({ queryKey: ['vision-providers'], queryFn: getVisionProviders })
  const conversations = useQuery({ queryKey: ['vqa-conversations', mediaId], queryFn: () => listConversations(mediaId) })
  const items = conversations.data ?? []
  const selected = selectedId === 'new' ? null : items.find(item => item.conversation_id === selectedId) ?? items[0] ?? null
  const ask = useMutation({ mutationFn: () => askVideo(mediaId, question.trim(), startMs, endMs, selected?.conversation_id ?? null, consent), onSuccess: result => {
    const record = result.conversation
    queryClient.setQueryData<VQAConversation[]>(['vqa-conversations', mediaId], old => [record, ...(old ?? []).filter(item => item.conversation_id !== record.conversation_id)])
    setSelectedId(record.conversation_id); setQuestion(''); onRefresh()
  } })
  const remove = useMutation({ mutationFn: () => deleteConversation(mediaId, selected!.conversation_id), onSuccess: () => { setSelectedId('new'); void queryClient.invalidateQueries({ queryKey: ['vqa-conversations', mediaId] }); onRefresh() } })
  return <section className="multimodal-inspector" aria-label="Video questions">
    <div className="section-label">VIDEO FRAME QUESTIONS</div>
    <p className="analysis-hint">OpenAI sees at most six actual sampled frames from the selected range, not continuous motion. Grounding is the model's assessment.</p>
    <p className="analysis-hint">Provider: {providers.data?.vqa.state ?? 'checking'}.</p>
    <label className="external-consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /> Allow this video's selected frames to be sent to OpenAI.</label>
    <div className="multimodal-actions"><button type="button" onClick={() => { setStartMs(currentMs); setEndMs(currentMs) }}>Use current frame ({time(currentMs)})</button><button type="button" onClick={() => setSelectedId('new')}>New conversation</button>{selected && <button type="button" disabled={remove.isPending} onClick={() => remove.mutate()}>Clear conversation</button>}</div>
    <div className="video-range"><label>Range start (s)<input aria-label="Video range start" type="number" min="0" max={durationMs / 1000} step="0.01" value={startMs / 1000} onChange={event => setStartMs(Math.round(Number(event.target.value) * 1000))} /></label><label>Range end (s)<input aria-label="Video range end" type="number" min="0" max={durationMs / 1000} step="0.01" value={endMs / 1000} onChange={event => setEndMs(Math.round(Number(event.target.value) * 1000))} /></label></div>
    {items.length > 0 && <label className="multimodal-field">Saved conversations<select aria-label="Saved video conversation" value={selected?.conversation_id ?? 'new'} onChange={event => setSelectedId(event.target.value)}><option value="new">New conversation</option>{items.map(item => <option key={item.conversation_id} value={item.conversation_id}>{new Date(item.updated_at).toLocaleString()} · {item.messages[0]?.text.slice(0, 30)}</option>)}</select></label>}
    <div className="vqa-messages" aria-live="polite">{selected?.messages.map(message => <article key={message.message_id} className={`vqa-message vqa-${message.role}`}><strong>{message.role === 'user' ? 'You' : 'Vision AI'}</strong><p>{message.text}</p>{message.frame_timestamps_ms && <div className="multimodal-actions">{message.frame_timestamps_ms.map(ms => <button key={ms} type="button" onClick={() => onSeek(ms)}>{time(ms)}</button>)}</div>}{message.role === 'assistant' && <small>Grounding: {message.grounding_status?.replace('_', ' ')} · {message.model} · {message.usage?.total_tokens ?? 'unknown'} tokens{message.uncertainty_note ? ` · ${message.uncertainty_note}` : ''}</small>}</article>) ?? <p className="analysis-message">Ask about selected frames.</p>}</div>
    <form onSubmit={event => { event.preventDefault(); if (question.trim()) ask.mutate() }}><label className="multimodal-field">Question<textarea aria-label="Question about video frames" value={question} maxLength={1000} onChange={event => setQuestion(event.target.value)} /></label><button type="submit" disabled={!question.trim() || !consent || !['configured', 'available'].includes(providers.data?.vqa.state ?? '') || startMs < 0 || endMs < startMs || endMs > durationMs || ask.isPending}>{ask.isPending ? 'Asking…' : 'Ask selected frames'}</button></form>
    {ask.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(ask.error)}</p>}
    {conversations.isError && <p role="alert" className="analysis-message analysis-error">{mediaErrorMessage(conversations.error)}</p>}
  </section>
}
