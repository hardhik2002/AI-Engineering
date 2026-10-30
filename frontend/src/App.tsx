import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
import { getCapabilities, getHealth } from '@/lib/api'
import { deleteMedia, formatBytes, listMedia, mediaErrorMessage } from '@/lib/media'
import { useMediaStore } from '@/store/media'
import { useThemeStore } from '@/store/theme'
import type { CapabilityId, CapabilityStatus } from '@/types/api'
import type { MediaAsset } from '@/types/media'

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
    icon: ScanEye, insight: 'Grounded image and region analysis arrives in Phase 4.',
  },
  {
    id: 'objects', name: 'Object and Region Understanding', shortName: 'Objects & regions',
    description: 'Inspect detected objects and their normalized locations.',
    icon: Box, insight: 'Real object detection and overlays arrive in Phase 3.',
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
  const current = modules.find((item) => item.id === moduleId)
  const theme = useThemeStore((state) => state.theme)
  const toggleTheme = useThemeStore((state) => state.toggleTheme)
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 30_000 })
  const capabilities = useQuery({ queryKey: ['capabilities'], queryFn: getCapabilities })
  const media = useQuery({ queryKey: ['media'], queryFn: listMedia, enabled: health.isSuccess })
  const queryClient = useQueryClient()
  const activeMediaId = useMediaStore((state) => state.activeMediaId)
  const selectMedia = useMediaStore((state) => state.selectMedia)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [uploadNotice, setUploadNotice] = useState('')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  if (!current) return <Navigate to="/workspace/captioning" replace />

  const currentCapability = capabilities.data?.find((item) => item.id === current.id)
  const apiState = health.isPending ? 'checking' : health.isError ? 'disconnected' : 'connected'
  const CurrentIcon = current.icon
  const assets = media.data ?? []
  const activeAsset = assets.find((asset) => asset.media_id === activeMediaId) ?? assets[0] ?? null

  function onUploaded(asset: MediaAsset) {
    setUploadNotice(`${asset.original_filename} uploaded and ready.`)
    selectMedia(asset.media_id)
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
          <div className="sidebar-info"><Layers3 size={16} /><span>Learning workspace</span><span className="phase-pill">PHASE 02</span></div>
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
            <span className="phase-badge"><span />Phase 2 media workspace</span>
          </div>
        </div>

        <section className="viewer-panel" aria-labelledby="viewer-title">
          <div className="panel-toolbar">
            <div className="panel-title"><span className="panel-title-icon"><ImageIcon size={17} /></span><span id="viewer-title">Media viewer</span><span className="panel-tag">{activeAsset ? activeAsset.media_type.toUpperCase() : 'NO MEDIA'}</span></div>
            <div className="viewer-actions">
              <span className="tool-label">Original media</span>
              {activeAsset && <><span className="vertical-rule" /><MediaUploader compact disabled={!health.isSuccess} onUploaded={onUploaded} /></>}
            </div>
          </div>
          {uploadNotice && <div className="upload-success-banner" role="status"><Check size={15} /><span>{uploadNotice}</span><button type="button" onClick={() => setUploadNotice('')} aria-label="Dismiss upload message">×</button></div>}
          <div className={`viewer-stage ${activeAsset ? 'has-media' : ''}`}>
            {activeAsset ? <MediaViewer asset={activeAsset} /> : health.isPending || media.isPending && health.isSuccess ?
              <div className="viewer-state">Loading media workspace…</div> : health.isError ?
                <div className="viewer-state">Backend disconnected. Start the API to upload media.</div> : <>
            <div className="stage-grid" aria-hidden="true" />
            <div className="stage-corner corner-tl" aria-hidden="true" /><div className="stage-corner corner-tr" aria-hidden="true" />
            <div className="stage-corner corner-bl" aria-hidden="true" /><div className="stage-corner corner-br" aria-hidden="true" />
            <MediaUploader onUploaded={onUploaded} />
            <span className="stage-coordinate stage-coordinate-top">X 00.000 &nbsp; Y 00.000</span>
            <span className="stage-coordinate stage-coordinate-bottom">VIEWPORT / EMPTY</span>
            </>}
          </div>
          <div className="viewer-footer"><span><span className="footer-dot" />{activeAsset ? activeAsset.original_filename : 'Awaiting media'}</span><span>{activeAsset ? `${activeAsset.width} × ${activeAsset.height} · ${formatBytes(activeAsset.file_size_bytes)}` : 'Overlays appear when providers are enabled'}</span></div>
        </section>

        <MediaLibrary assets={assets} activeId={activeAsset?.media_id ?? null} onSelect={selectMedia} loading={health.isPending || (media.isPending && health.isSuccess)} error={media.isError || health.isError} onRetry={() => { void health.refetch(); void media.refetch() }} />

        <section className="foundation-strip" aria-label="Phase two progress">
          <div className="foundation-icon"><Check size={18} /></div>
          <div><strong>Media workspace active</strong><span>Upload, inspect and reopen real media across all five modules.</span></div>
          <span className="foundation-index">02 / 08</span>
        </section>
      </main>

      <aside className="inspector" aria-label="AI results inspector">
        <div className="inspector-header"><div><span className="inspector-overline">INTELLIGENCE PANEL</span><h2>AI Inspector</h2></div><Sparkles size={19} /></div>
        <div className="inspector-tabs"><span className="inspector-tab active">Overview</span></div>
        <div className="inspector-content">
          <div className="inspector-empty"><div className="inspector-empty-icon"><WandSparkles size={22} /></div><strong>No AI analysis yet</strong><p>Inference is planned for later phases. Model results will be linked to this media when available.</p></div>
          <MediaInspector asset={activeAsset} onDelete={(id) => void onDelete(id)} deleting={deleting} error={deleteError} />
          <div className="inspector-section"><div className="section-label">SELECTED MODULE</div><div className="capability-card"><div className="capability-card-top"><span className="capability-icon"><CurrentIcon size={18} /></span><StatusLabel status={currentCapability?.status ?? 'unknown'} /></div><strong>{current.name}</strong><p>{current.insight}</p><div className="capability-card-foot"><span>Planned integration</span><span>Phase {currentCapability?.phase ?? '—'}</span></div></div></div>
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

