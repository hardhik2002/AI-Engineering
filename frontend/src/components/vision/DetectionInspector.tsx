import type { AnalysisRecord, DetectedObject, ModelStatus } from '@/types/vision'

interface Props {
  analysis: AnalysisRecord | null
  model: ModelStatus | null
  loading: boolean
  error: string
  visible: DetectedObject[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  displayConfidence: number
  onDisplayConfidence: (value: number) => void
  selectedClasses: string[]
  onSelectedClasses: (value: string[]) => void
  showBoxes: boolean
  onShowBoxes: (value: boolean) => void
  showLabels: boolean
  onShowLabels: (value: boolean) => void
  showConfidence: boolean
  onShowConfidence: (value: boolean) => void
  onReset: () => void
}

const percent = (value: number) => `${Math.round(value * 100)}%`

export function DetectionInspector({ analysis, model, loading, error, visible, selectedId, onSelect,
  displayConfidence, onDisplayConfidence, selectedClasses, onSelectedClasses,
  showBoxes, onShowBoxes, showLabels, onShowLabels, showConfidence, onShowConfidence, onReset }: Props) {
  const all = analysis?.detections ?? []
  const classes = Object.keys(analysis?.summary?.class_counts ?? {})
  const selectedIndex = visible.findIndex((item) => item.id === selectedId)
  const selected = visible[selectedIndex]
  const counts = classes.map((label) => ({ label, count: visible.filter((item) => item.label === label).length }))
  const maxCount = Math.max(1, ...counts.map((item) => item.count))
  return <div className="detection-inspector">
    {loading && <div className="analysis-message" role="status">Running YOLO26 image detection… This may take longer on CPU or on the first run.<div className="analysis-progress" role="progressbar" aria-label="Image analysis in progress"><i /></div></div>}
    {error && <div className="analysis-message analysis-error" role="alert">{error}</div>}
    {model && model.state !== 'ready' && !analysis && <div className="analysis-message">Model: {model.state.replace('_', ' ')}. {model.detail}</div>}
    {!analysis && !loading && <div className="inspector-empty"><strong>No object analysis yet</strong><p>Select an uploaded image and run Analyze Image. Results are saved locally.</p></div>}
    {analysis?.status === 'failed' && <div className="analysis-message analysis-error">This saved analysis failed ({analysis.error_code}). Run a new analysis to retry.</div>}
    {analysis?.status === 'completed' && <>
      <div className="analysis-stats"><div><strong>{visible.length}</strong><span>visible objects</span></div><div><strong>{analysis.summary?.total_objects ?? 0}</strong><span>detected in run</span></div><div><strong>{analysis.timings_ms?.total.toFixed(0) ?? '—'} ms</strong><span>total time</span></div></div>
      <div className="analysis-meta">{analysis.model?.name} · {analysis.model?.device} · Ultralytics {analysis.model?.package_version}<br />{new Date(analysis.completed_at).toLocaleString()}</div>
      <div className="analysis-section"><div className="section-label">DISPLAY FILTERS</div>
        <label className="analysis-range">Minimum visible confidence <strong>{percent(displayConfidence)}</strong><input aria-label="Display confidence" type="range" min="0" max="1" step="0.01" value={displayConfidence} onChange={(event) => onDisplayConfidence(Number(event.target.value))} /></label>
        <div className="analysis-checks">
          <label><input type="checkbox" checked={showBoxes} onChange={(event) => onShowBoxes(event.target.checked)} /> Show boxes</label>
          <label><input type="checkbox" checked={showLabels} onChange={(event) => onShowLabels(event.target.checked)} /> Show labels</label>
          <label><input type="checkbox" checked={showConfidence} onChange={(event) => onShowConfidence(event.target.checked)} /> Show confidence</label>
        </div>
        {classes.length > 0 && <div className="analysis-classes" aria-label="Class filters">{classes.map((label) => <label key={label}><input type="checkbox" checked={!selectedClasses.includes(label)} onChange={(event) => onSelectedClasses(event.target.checked ? selectedClasses.filter((item) => item !== label) : [...selectedClasses, label])} /> {label}</label>)}</div>}
        <button type="button" className="analysis-text-button" onClick={onReset}>Reset visualization controls</button>
        <p className="analysis-hint">Display filters use saved results. Detection confidence is a model score, not a guarantee.</p>
      </div>
      <div className="analysis-section"><div className="section-label">CLASS DISTRIBUTION</div>
        {counts.filter((item) => item.count).length ? counts.filter((item) => item.count).map((item) => <div className="class-bar" key={item.label}><span>{item.label}</span><div><i style={{ width: `${item.count / maxCount * 100}%` }} /></div><strong>{item.count}</strong></div>) : <p className="analysis-hint">No classes pass the display filters.</p>}
      </div>
      <div className="analysis-section"><div className="section-label">DETECTED OBJECTS</div>
        {all.length === 0 ? <p className="analysis-hint">No supported objects were detected at this inference threshold. The image may still contain other content.</p> : visible.length === 0 ? <p className="analysis-hint">No detections pass the display filters.</p> : <div className="object-list">{visible.map((item) => <button key={item.id} type="button" className={item.id === selectedId ? 'selected' : ''} onClick={() => onSelect(item.id)} aria-pressed={item.id === selectedId}><span>{item.label}</span><strong>{percent(item.confidence)}</strong></button>)}</div>}
      </div>
      {selected && analysis.image && <div className="analysis-section selected-object"><div className="section-label">SELECTED OBJECT</div><strong>{selected.label} · {percent(selected.confidence)}</strong>
        <dl><div><dt>ID</dt><dd>{selected.id}</dd></div><div><dt>Normalized box</dt><dd>{Object.values(selected.bounding_box).map((value) => value.toFixed(4)).join(', ')}</dd></div><div><dt>Pixels (x, y, w, h)</dt><dd>{[selected.bounding_box.x * analysis.image.width, selected.bounding_box.y * analysis.image.height, selected.bounding_box.width * analysis.image.width, selected.bounding_box.height * analysis.image.height].map(Math.round).join(', ')}</dd></div><div><dt>Model</dt><dd>{analysis.model?.name}</dd></div></dl>
        <div className="object-navigation"><button type="button" onClick={() => onSelect(visible[(selectedIndex - 1 + visible.length) % visible.length].id)}>Previous</button><button type="button" onClick={() => onSelect(null)}>Deselect</button><button type="button" onClick={() => onSelect(visible[(selectedIndex + 1) % visible.length].id)}>Next</button></div>
      </div>}
    </>}
  </div>
}
