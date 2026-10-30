import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { CaptionMode, CaptionModelStatus, CaptionRecord } from '@/types/caption'

interface Props {
  imageReady: boolean
  model: CaptionModelStatus | null
  records: CaptionRecord[]
  selected: CaptionRecord | null
  selectedRegionId: string | null
  showRegions: boolean
  onShowRegions: (value: boolean) => void
  onSelectRecord: (id: string) => void
  onSelectRegion: (id: string) => void
  onGenerate: (mode: CaptionMode) => void
  onDense: () => void
  loading: boolean
  historyLoading: boolean
  error: string
}

export function CaptionInspector({ imageReady, model, records, selected, selectedRegionId, showRegions,
  onShowRegions, onSelectRecord, onSelectRegion, onGenerate, onDense, loading, historyLoading, error }: Props) {
  const [mode, setMode] = useState<CaptionMode>('short')
  const [copied, setCopied] = useState(false)
  const region = selected?.regions.find((item) => item.id === selectedRegionId)
  return <div className="detection-inspector caption-inspector">
    <div className="analysis-section"><div className="section-label">FLORENCE-2 CAPTIONING</div>
      <p className="analysis-hint">{model ? `Model ${model.state.replaceAll('_', ' ')} · ${model.device ?? 'device selected on load'}` : 'Checking Florence model…'}</p>
      <label className="caption-mode">Caption mode <select aria-label="Caption mode" value={mode} onChange={(event) => setMode(event.target.value as CaptionMode)}>
        <option value="short">Short</option><option value="detailed">Detailed</option><option value="extended">Extended</option>
      </select></label>
      <div className="caption-actions"><Button type="button" onClick={() => onGenerate(mode)} disabled={!imageReady || loading}>{selected?.task === mode ? 'Regenerate Caption' : 'Generate Caption'}</Button>
        <Button type="button" variant="ghost" onClick={onDense} disabled={!imageReady || loading}>Generate Dense Regions</Button></div>
      {!imageReady && <p className="analysis-hint">Select an uploaded image to use Florence-2.</p>}
    </div>
    {loading && <div className="analysis-message" role="status">Generating with Florence-2… Initial model loading may take longer on CPU.<div className="analysis-progress" role="progressbar" aria-label="Caption generation in progress"><i /></div></div>}
    {historyLoading && <div className="analysis-message" role="status">Loading saved captions…</div>}
    {error && <div className="analysis-message analysis-error" role="alert">{error}</div>}
    {selected && <div className="analysis-section"><div className="section-label">SAVED RESULT · {selected.task.replaceAll('_', ' ').toUpperCase()}</div>
      {selected.text && <><p className="caption-text">{selected.text}</p><Button type="button" variant="ghost" onClick={() => { void navigator.clipboard.writeText(selected.text ?? '').then(() => setCopied(true)) }}>{copied ? 'Copied' : 'Copy Caption'}</Button></>}
      <p className="analysis-hint">{selected.model.checkpoint} · {selected.model.device} · {selected.inference_ms.toFixed(0)} ms inference · {selected.model_load_ms.toFixed(0)} ms model load<br />{new Date(selected.completed_at).toLocaleString()}</p>
      {selected.task === 'dense' && <><label className="analysis-checks"><input type="checkbox" checked={showRegions} onChange={(event) => onShowRegions(event.target.checked)} /> Show Florence regions</label>
        <div className="object-list" aria-label="Dense regions">{selected.regions.length ? selected.regions.map((item, index) => <button key={item.id} type="button" className={item.id === selectedRegionId ? 'selected' : ''} onClick={() => onSelectRegion(item.id)} aria-pressed={item.id === selectedRegionId}>Region {index + 1}: {item.description}</button>) : <p className="analysis-hint">No regions returned by the model.</p>}</div>
        {region && <div className="selected-object"><strong>{region.description}</strong><p className="analysis-hint">Normalized box: {Object.values(region.bounding_box).map((value) => value.toFixed(4)).join(', ')}</p></div>}</>}
    </div>}
    <div className="analysis-section"><div className="section-label">SAVED CAPTIONS</div>
      {records.length ? <label className="caption-mode">View saved result <select aria-label="Saved caption" value={selected?.analysis_id ?? records[0].analysis_id} onChange={(event) => { onSelectRecord(event.target.value); setCopied(false) }}>
        {records.filter((item) => item.task !== 'selected_object').map((item) => <option key={item.analysis_id} value={item.analysis_id}>{item.task} · {new Date(item.created_at).toLocaleString()}</option>)}</select></label> : <p className="analysis-hint">No captions saved for this image.</p>}
    </div>
  </div>
}
