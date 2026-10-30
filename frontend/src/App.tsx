import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Accessibility, ArrowRight, Box, Check, ChevronDown, CircleHelp, CloudOff,
  Image as ImageIcon, Layers3, MessageCircleQuestion, Moon, PanelRightClose,
  ScanEye, Sparkles, Sun, Upload, WandSparkles,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { getCapabilities, getHealth } from '@/lib/api'
import { useThemeStore } from '@/store/theme'
import type { CapabilityId, CapabilityStatus } from '@/types/api'

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

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  if (!current) return <Navigate to="/workspace/captioning" replace />

  const currentCapability = capabilities.data?.find((item) => item.id === current.id)
  const apiState = health.isPending ? 'checking' : health.isError ? 'disconnected' : 'connected'
  const CurrentIcon = current.icon

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
          <div className="sidebar-info"><Layers3 size={16} /><span>Learning workspace</span><span className="phase-pill">PHASE 01</span></div>
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
            <span className="phase-badge"><span />Phase 1 foundation</span>
          </div>
        </div>

        <section className="viewer-panel" aria-labelledby="viewer-title">
          <div className="panel-toolbar">
            <div className="panel-title"><span className="panel-title-icon"><ImageIcon size={17} /></span><span id="viewer-title">Media viewer</span><span className="panel-tag">NO MEDIA</span></div>
            <div className="viewer-actions">
              <span className="tool-label">Original media</span>
              <ChevronDown size={15} className="muted-icon" aria-hidden="true" />
              <span className="vertical-rule" />
              <Button variant="ghost" size="icon" disabled aria-label="Viewer settings unavailable until media upload" title="Available in Phase 2"><PanelRightClose size={17} /></Button>
            </div>
          </div>
          <div className="viewer-stage">
            <div className="stage-grid" aria-hidden="true" />
            <div className="stage-corner corner-tl" aria-hidden="true" /><div className="stage-corner corner-tr" aria-hidden="true" />
            <div className="stage-corner corner-bl" aria-hidden="true" /><div className="stage-corner corner-br" aria-hidden="true" />
            <div className="empty-visual">
              <div className="empty-icon-wrap"><div className="empty-icon-halo" /><ImageIcon size={28} strokeWidth={1.5} /></div>
              <div className="empty-eyebrow">YOUR CANVAS IS READY</div>
              <h2>No media loaded</h2>
              <p>Secure image and video upload will be available in Phase 2. Analysis will always appear alongside the original media.</p>
              <Button disabled title="Media upload arrives in Phase 2"><Upload size={16} />Upload media <span className="button-soon">SOON</span></Button>
            </div>
            <span className="stage-coordinate stage-coordinate-top">X 00.000 &nbsp; Y 00.000</span>
            <span className="stage-coordinate stage-coordinate-bottom">VIEWPORT / EMPTY</span>
          </div>
          <div className="viewer-footer"><span><span className="footer-dot" />Awaiting media</span><span>Overlays appear here when providers are enabled</span></div>
        </section>

        <section className="foundation-strip" aria-label="Phase one progress">
          <div className="foundation-icon"><Check size={18} /></div>
          <div><strong>Foundation active</strong><span>Application shell, typed API contracts, configuration and structured logging.</span></div>
          <span className="foundation-index">01 / 08</span>
        </section>
      </main>

      <aside className="inspector" aria-label="AI results inspector">
        <div className="inspector-header"><div><span className="inspector-overline">INTELLIGENCE PANEL</span><h2>AI Inspector</h2></div><Sparkles size={19} /></div>
        <div className="inspector-tabs"><span className="inspector-tab active">Results</span><span className="inspector-tab">Details</span></div>
        <div className="inspector-content">
          <div className="inspector-empty"><div className="inspector-empty-icon"><WandSparkles size={22} /></div><strong>No analysis yet</strong><p>Results from real models will appear here with confidence, source context and model provenance.</p></div>
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

