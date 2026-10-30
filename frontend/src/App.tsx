import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMutation } from '@tanstack/react-query'
import {
  Accessibility, ArrowRight, Box, Check, CircleHelp, CloudOff,
  Image as ImageIcon, Layers3, MessageCircleQuestion, Moon,
  ScanEye, Sparkles, Sun, WandSparkles,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { MediaInspector } from '@/components/media/MediaInspector'
import { MediaLibrary } from '@/components/media/MediaLibrary'
import { MediaUploader } from '@/components/media/MediaUploader'
import { MediaViewer } from '@/components/media/MediaViewer'
import { DetectionInspector } from '@/components/vision/DetectionInspector'
import { getCapabilities, getHealth } from '@/lib/api'
import { deleteMedia, formatBytes, getMediaLimits, listMedia, mediaErrorMessage } from '@/lib/media'
import { analyzeImage, getModels, listAnalyses } from '@/lib/vision'
import { useMediaStore } from '@/store/media'
import { useThemeStore } from '@/store/theme'
import type { CapabilityId, CapabilityStatus } from '@/types/api'
import type { MediaAsset } from '@/types/media'
import type { AnalysisRecord, DetectionParameters } from '@/types/vision'

interface ModuleInfo {
  id: CapabilityId
  name: string
  shortName: string
  description: string
  icon: LucideIcon
  insight: string
}

const modules: ModuleInfo[] = [
  {
    id: 'captioning', name: 'Image Captioning', shortName: 'Captioning',
    description: 'Generate concise captions grounded in what a model actually sees.',
    icon: ImageIcon, insight: 'Florence-2 captions and source-linked results arrive in Phase 4.',
  },
  {
    id: 'vqa', name: 'Visual Question Answering', shortName: 'Visual Q&A',
    description: 'Ask questions about an image or selected video frame.',
    icon: MessageCircleQuestion, insight: 'Optional OpenAI vision Q&A arrives in Phase 5.',
  },
  {
    id: 'analysis', name: 'Image Analysis', shortName: 'Analysis',
    description: 'Explore image content with evidence tied to the original media.',
    icon: ScanEye, insight: 'YOLO26 detects supported object classes. Broader scene analysis arrives in Phase 4.',
  },
  {
    id: 'objects', name: 'Object and Region Understanding', shortName: 'Objects & regions',
    description: 'Inspect detected objects and their normalized locations.',
    icon: Box, insight: 'YOLO26 object boxes are available for images. Region descriptions arrive in Phase 4.',
  },
  {
    id: 'accessibility', name: 'Accessible Image Descriptions', shortName: 'Accessibility',
    description: 'Create useful descriptions for people using assistive technology.',
    icon: Accessibility, insight: 'Accessible descriptions arrive in Phase 5.',
  },
]

function StatusLabel({ status }: { status: CapabilityStatus | 'unknown' }) {
  return <span className={`module-status module-status-${status}`}>
    <span className="status-dot" />{status === 'unknown' ? 'Unknown' : status}
  </span>
}

function Workstation() {
  const { moduleId } = useParams()
  const current = modules.find((item) => item.id === moduleId) ?? modules[0]
  const theme = useThemeStore((state) => state.theme)
  const toggleTheme = useThemeStore((state) => state.toggleTheme)
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 30_000 })
  const capabilities = useQuery({ queryKey: ['capabilities'], queryFn: getCapabilities })
  const media = useQuery({ queryKey: ['media'], queryFn: listMedia, enabled: health.isSuccess })
  const limits = useQuery({ queryKey: ['media-limits'], queryFn: getMediaLimits, enabled: health.isSuccess })
  const queryClient = useQueryClient()
  const activeMediaId = useMediaStore((state) => state.activeMediaId)
  const selectMedia = useMediaStore((state) => state.selectMedia)
  const activeAnalysisId = useMediaStore((state) => state.activeAnalysisId)
  const selectAnalysis = useMediaStore((state) => state.selectAnalysis)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [uploadNotice, setUploadNotice] = useState('')
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null)
  const [displayConfidence, setDisplayConfidence] = useState(0)
  const [excludedClasses, setExcludedClasses] = useState<string[]>([])
  const [showBoxes, setShowBoxes] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [showConfidence, setShowConfidence] = useState(true)
  const [inferenceParameters, setInferenceParameters] = useState<DetectionParameters>({ confidence: 0.25, iou: 0.45, image_size: 640, max_detections: 100 })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const currentCapability = capabilities.data?.find((item) => item.id === current.id)
  const apiState = health.isPending ? 'checking' : health.isError ? 'disconnected' : 'connected'
  const CurrentIcon = current.icon
  const assets = media.data ?? []
  const activeAsset = assets.find((asset) => asset.media_id === activeMediaId) ?? assets[0] ?? null
  const detectionModule = current.id === 'analysis' || current.id === 'objects'
  const imageForAnalysis = detectionModule && activeAsset?.media_type === 'image' ? activeAsset : null
  const modelQuery = useQuery({ queryKey: ['vision-models'], queryFn: getModels, enabled: health.isSuccess && detectionModule, refetchInterval: 15000 })
  const analysesQuery = useQuery({ queryKey: ['analyses', imageForAnalysis?.media_id], queryFn: () => listAnalyses(imageForAnalysis!.media_id), enabled: !!imageForAnalysis && health.isSuccess })
  const runAnalysis = useMutation({ mutationFn: () => analyzeImage(imageForAnalysis!.media_id, inferenceParameters), onSuccess: (record) => {
    selectAnalysis(record.analysis_id)
    setSelectedObjectId(null)
    queryClient.setQueryData<AnalysisRecord[]>(['analyses', record.media_id], (current) => [record, ...(current ?? [])])
    void queryClient.invalidateQueries({ queryKey: ['vision-models'] })
    void queryClient.invalidateQueries({ queryKey: ['capabilities'] })
  } })
  const analyses = analysesQuery.data ?? []
  const analysis = analyses.find((item) => item.analysis_id === activeAnalysisId) ?? analyses[0] ?? null
  const visibleObjects = (analysis?.detections ?? []).filter((item) => item.confidence >= displayConfidence && !excludedClasses.includes(item.label))
  const overlays = detectionModule && showBoxes ? visibleObjects.map((item) => ({ id: item.id, classId: item.class_id,
    label: item.label, confidence: item.confidence, box: { x1: item.bounding_box.x, y1: item.bounding_box.y,
      x2: item.bounding_box.x + item.bounding_box.width, y2: item.bounding_box.y + item.bounding_box.height } })) : []

  function resetDisplay() { setDisplayConfidence(0); setExcludedClasses([]); setShowBoxes(true); setShowLabels(true); setShowConfidence(true) }

  function onUploaded(asset: MediaAsset) {
    setUploadNotice(`${asset.original_filename} uploaded and ready.`)
    selectMedia(asset.media_id)
    setSelectedObjectId(null)
    resetDisplay()
    queryClient.setQueryData<MediaAsset[]>(['media'], (current) =>
      [asset, ...(current ?? []).filter((item) => item.media_id !== asset.media_id)])
    void queryClient.invalidateQueries({ queryKey: ['media'] })
  }

  async function onDelete(mediaId: string) {
    if (!window.confirm('Delete this media file from your local library?')) return
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteMedia(mediaId)
      selectMedia(assets.find((asset) => asset.media_id !== mediaId)?.media_id ?? null)
      queryClient.removeQueries({ queryKey: ['analyses', mediaId] })
      queryClient.setQueryData<MediaAsset[]>(['media'], (current) =>
        (current ?? []).filter((item) => item.media_id !== mediaId))
      await queryClient.invalidateQueries({ queryKey: ['media'] })
    } catch (error) { setDeleteError(mediaErrorMessage(error)) }
    finally { setDeleting(false) }
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to workspace</a>
    <header className="topbar">
      <div className="brand" aria-label="VisionLab AI">
        <span className="brand-mark"><ScanEye size={21} strokeWidth={2.2} /></span>
        <span className="brand-word">vision<span>lab</span><small>AI</small></span>
        <span className="brand-divider" />
        <span className="brand-product">Computer vision workstation</span>
      </div>
      <div className="topbar-actions">
        <span className={`connection connection-${apiState}`} role="status">
          <span className="connection-indicator" />
          <span className="connection-label">{apiState === 'connected' ? 'API connected' : apiState === 'checking' ? 'Checking API' : 'API disconnected'}</span>
        </span>
        <span className="topbar-divider" />
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </Button>
        <span className="avatar" aria-hidden="true">VL</span>
      </div>
    </header>

    <div className="workspace-grid">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar-heading"><span>WORKSPACE</span><span className="sidebar-heading-line" /></div>
        <nav className="module-nav" aria-label="Vision modules">
          {modules.map((module) => {
            const Icon = module.icon
            const status = capabilities.data?.find((item) => item.id === module.id)?.status ?? 'unknown'
            return <NavLink key={module.id} to={`/workspace/${module.id}`} className={({ isActive }) => `module-link ${isActive ? 'active' : ''}`}>
              <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
              <span className="module-link-label">{module.shortName}</span>
              <span className={`nav-dot nav-dot-${status}`} aria-hidden="true" />
            </NavLink>
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-info"><Layers3 size={16} /><span>Learning workspace</span><span className="phase-pill">PHASE 03</span></div>
          <div className="sidebar-note">Explore five image-understanding capabilities as each real provider is integrated.</div>
        </div>
      </aside>

      <main className="main-panel" id="main-content">
        <div className="page-heading">
          <div>
            <div className="breadcrumb"><span>Workspace</span><ArrowRight size={13} /><span>{current.shortName}</span></div>
            <div className="title-row"><span className="title-icon"><CurrentIcon size={23} strokeWidth={1.8} /></span><h1>{current.name}</h1></div>
            <p>{current.description}</p>
          </div>
          <div className="heading-actions">
            <span className="phase-badge"><span />Phase 3 object detection</span>
          </div>
        </div>

        <section className="viewer-panel" aria-labelledby="viewer-title">
          <div className="panel-toolbar">
            <div className="panel-title"><span className="panel-title-icon"><ImageIcon size={17} /></span><span id="viewer-title">Media viewer</span><span className="panel-tag">{activeAsset ? activeAsset.media_type.toUpperCase() : 'NO MEDIA'}</span></div>
            <div className="viewer-actions">
              <span className="tool-label">Original media</span>
              {activeAsset && <><span className="vertical-rule" /><MediaUploader compact disabled={!health.isSuccess} limits={limits.data} onUploaded={onUploaded} /></>}
            </div>
          </div>
          {uploadNotice && <div className="upload-success-banner" role="status"><Check size={15} /><span>{uploadNotice}</span><button type="button" onClick={() => setUploadNotice('')} aria-label="Dismiss upload message">×</button></div>}
          <div className={`viewer-stage ${activeAsset ? 'has-media' : ''}`}>
            {activeAsset ? <MediaViewer asset={activeAsset} detections={overlays} selectedId={selectedObjectId} onSelect={setSelectedObjectId} showLabels={showLabels} showConfidence={showConfidence} /> : health.isPending || media.isPending && health.isSuccess ?
              <div className="viewer-state">Loading media workspace…</div> : health.isError ?
                <div className="viewer-state">Backend disconnected. Start the API to upload media.</div> : <>
            <div className="stage-grid" aria-hidden="true" />
            <div className="stage-corner corner-tl" aria-hidden="true" /><div className="stage-corner corner-tr" aria-hidden="true" />
            <div className="stage-corner corner-bl" aria-hidden="true" /><div className="stage-corner corner-br" aria-hidden="true" />
            <MediaUploader limits={limits.data} onUploaded={onUploaded} />
            <span className="stage-coordinate stage-coordinate-top">X 00.000 &nbsp; Y 00.000</span>
            <span className="stage-coordinate stage-coordinate-bottom">VIEWPORT / EMPTY</span>
            </>}
          </div>
          <div className="viewer-footer"><span><span className="footer-dot" />{activeAsset ? activeAsset.original_filename : 'Awaiting media'}</span><span>{activeAsset ? `${activeAsset.width} × ${activeAsset.height} · ${formatBytes(activeAsset.file_size_bytes)}` : 'Overlays appear when providers are enabled'}</span></div>
        </section>

        {detectionModule && <section className="analysis-run-panel" aria-label="Image detection controls">
          <div><strong>YOLO26 Nano · Image detection</strong><span>{activeAsset?.media_type === 'video' ? 'Video analysis is planned for Phase 6.' : imageForAnalysis ? `Model ${modelQuery.data?.[0]?.state.replace('_', ' ') ?? 'checking'} · ${analyses.length} saved run${analyses.length === 1 ? '' : 's'}` : 'Select or upload an image to begin.'}</span></div>
          {imageForAnalysis && <>
            <div className="inference-fields"><label>Inference confidence <input aria-label="Inference confidence" type="number" min="0.01" max="1" step="0.01" value={inferenceParameters.confidence} onChange={(event) => setInferenceParameters({ ...inferenceParameters, confidence: Number(event.target.value) })} /></label><label>IoU <input aria-label="Inference IoU" type="number" min="0" max="1" step="0.01" value={inferenceParameters.iou} onChange={(event) => setInferenceParameters({ ...inferenceParameters, iou: Number(event.target.value) })} /></label></div>
            <Button type="button" onClick={() => runAnalysis.mutate()} disabled={runAnalysis.isPending || inferenceParameters.confidence <= 0 || inferenceParameters.confidence > 1 || inferenceParameters.iou < 0 || inferenceParameters.iou > 1}>{runAnalysis.isPending ? 'Analyzing…' : analysis ? 'Re-run Analysis' : 'Analyze Image'}</Button>
            {analyses.length > 1 && <label className="analysis-run-select">Saved run <select aria-label="Saved analysis" value={analysis?.analysis_id} onChange={(event) => { selectAnalysis(event.target.value); setSelectedObjectId(null) }}>{analyses.map((item) => <option key={item.analysis_id} value={item.analysis_id}>{new Date(item.created_at).toLocaleString()} · {item.status}</option>)}</select></label>}
          </>}
        </section>}

        <MediaLibrary assets={assets} activeId={activeAsset?.media_id ?? null} onSelect={(id) => { selectMedia(id); setSelectedObjectId(null); resetDisplay() }} loading={health.isPending || (media.isPending && health.isSuccess)} error={media.isError || health.isError} onRetry={() => { void health.refetch(); void media.refetch() }} />

        <section className="foundation-strip" aria-label="Phase three progress">
          <div className="foundation-icon"><Check size={18} /></div>
          <div><strong>Image detection workspace active</strong><span>Analyze uploaded images with a local model and reopen saved results.</span></div>
          <span className="foundation-index">03 / 08</span>
        </section>
      </main>

      <aside className="inspector" aria-label="AI results inspector">
        <div className="inspector-header"><div><span className="inspector-overline">INTELLIGENCE PANEL</span><h2>AI Inspector</h2></div><Sparkles size={19} /></div>
        <div className="inspector-tabs"><span className="inspector-tab active">Overview</span></div>
        <div className="inspector-content">
          {detectionModule ? <DetectionInspector analysis={analysis} model={modelQuery.data?.[0] ?? null} loading={runAnalysis.isPending || analysesQuery.isPending && !!imageForAnalysis} error={runAnalysis.isError ? mediaErrorMessage(runAnalysis.error) : analysesQuery.isError ? mediaErrorMessage(analysesQuery.error) : ''} visible={visibleObjects} selectedId={selectedObjectId} onSelect={setSelectedObjectId} displayConfidence={displayConfidence} onDisplayConfidence={setDisplayConfidence} selectedClasses={excludedClasses} onSelectedClasses={setExcludedClasses} showBoxes={showBoxes} onShowBoxes={setShowBoxes} showLabels={showLabels} onShowLabels={setShowLabels} showConfidence={showConfidence} onShowConfidence={setShowConfidence} onReset={resetDisplay} /> : <div className="inspector-empty"><div className="inspector-empty-icon"><WandSparkles size={22} /></div><strong>No AI analysis yet</strong><p>This capability is planned for a later phase.</p></div>}
          <MediaInspector asset={activeAsset} onDelete={(id) => void onDelete(id)} deleting={deleting} error={deleteError} />
          <div className="inspector-section"><div className="section-label">SELECTED MODULE</div><div className="capability-card"><div className="capability-card-top"><span className="capability-icon"><CurrentIcon size={18} /></span><StatusLabel status={currentCapability?.status ?? 'unknown'} /></div><strong>{current.name}</strong><p>{current.insight}</p><div className="capability-card-foot"><span>Integration</span><span>Phase {currentCapability?.phase ?? '—'}</span></div></div></div>
          <div className="inspector-section"><div className="section-label">SYSTEM STATUS</div>
            {health.isSuccess && health.data ? <div className="system-row"><span className="system-icon online"><Check size={16} /></span><div><strong>Backend online</strong><span>Version {health.data.version} · {health.data.environment}</span></div></div> :
              apiState === 'checking' ? <div className="system-row"><span className="system-icon checking"><CircleHelp size={16} /></span><div><strong>Connecting to backend</strong><span>Checking local API health…</span></div></div> :
                <div className="system-row"><span className="system-icon offline"><CloudOff size={16} /></span><div><strong>Backend unavailable</strong><span>Start FastAPI at localhost:5200.</span></div></div>}
            {capabilities.isError && <div className="capability-error">Capability status unavailable. <button type="button" onClick={() => capabilities.refetch()}>Retry</button></div>}
          </div>
        </div>
        <div className="inspector-footer"><span className="footer-spark"><Sparkles size={15} /></span><span>Grounded results only. No simulated inference.</span></div>
      </aside>
    </div>
  </div>
}

export default function App() {
  return <Routes><Route path="/" element={<Navigate to="/workspace/captioning" replace />} /><Route path="/workspace/:moduleId" element={<Workstation />} /><Route path="*" element={<Navigate to="/workspace/captioning" replace />} /></Routes>
}

