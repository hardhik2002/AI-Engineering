import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMutation } from '@tanstack/react-query'
import {
  Accessibility, ArrowRight, Box, Camera, Check, CircleHelp, CloudOff,
  Image as ImageIcon, Layers3, MessageCircleQuestion, Moon,
  ScanEye, Sparkles, Sun, WandSparkles,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { MediaInspector } from '@/components/media/MediaInspector'
import { MediaLibrary } from '@/components/media/MediaLibrary'
import { MediaUploader } from '@/components/media/MediaUploader'
import { MediaViewer } from '@/components/media/MediaViewer'
import { DetectionInspector } from '@/components/vision/DetectionInspector'
import { CaptionInspector } from '@/components/vision/CaptionInspector'
import { VQAInspector } from '@/components/vision/VQAInspector'
import { AccessibilityInspector } from '@/components/vision/AccessibilityInspector'
import { VideoAnalysisControls, VideoCaptionInspector, VideoDetectionInspector, VideoVQAInspector } from '@/components/vision/VideoPanels'
import { LiveCameraInspector, LiveCameraStage } from '@/components/live/LiveCameraWorkspace'
import { useLiveCamera } from '@/components/live/useLiveCamera'
import { closestAnalyzedFrame } from '@/lib/videoFrame'
import { getCapabilities, getHealth } from '@/lib/api'
import { deleteMedia, formatBytes, getMediaLimits, listMedia, mediaErrorMessage } from '@/lib/media'
import { analyzeImage, getModels, listAnalyses } from '@/lib/vision'
import { describeObject, generateCaption, generateDenseRegions, getCaptionModel, listCaptions } from '@/lib/caption'
import { listConversations } from '@/lib/multimodal'
import { activeJob, getVideoCaptions, getVideoFrames, getVideoJob, getVideoTimeline, getVideoTracks, listVideoAnalyses, startVideoAnalysis } from '@/lib/video'
import { useMediaStore } from '@/store/media'
import { useThemeStore } from '@/store/theme'
import type { CapabilityId, CapabilityStatus } from '@/types/api'
import type { MediaAsset } from '@/types/media'
import type { AnalysisRecord, DetectionParameters } from '@/types/vision'
import type { CaptionMode, CaptionRecord } from '@/types/caption'
import type { TimestampedAnalysisResult } from '@/types/media'
import type { VideoParameters } from '@/types/video'

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
    description: 'Generate captions for images and sampled video frames.',
    icon: ImageIcon, insight: 'Florence-2 captions are tied to actual image regions or video timestamps.',
  },
  {
    id: 'vqa', name: 'Visual Question Answering', shortName: 'Visual Q&A',
    description: 'Ask grounded questions about images or selected video frames.',
    icon: MessageCircleQuestion, insight: 'Optional OpenAI vision Q&A requires a backend key and media-specific consent.',
  },
  {
    id: 'analysis', name: 'Image Analysis', shortName: 'Analysis',
    description: 'Explore image content with evidence tied to the original media.',
    icon: ScanEye, insight: 'YOLO26 detects supported object classes; Florence-2 captions are available in Captioning.',
  },
  {
    id: 'objects', name: 'Object and Region Understanding', shortName: 'Objects & regions',
    description: 'Inspect detected objects and their normalized locations.',
    icon: Box, insight: 'Inspect YOLO26 boxes and describe a selected object with Florence-2.',
  },
  {
    id: 'accessibility', name: 'Accessible Image Descriptions', shortName: 'Accessibility',
    description: 'Create useful descriptions for people using assistive technology.',
    icon: Accessibility, insight: 'Edit image alt text and timestamped video scene descriptions.',
  },
  {
    id: 'live_camera', name: 'Live Camera', shortName: 'Live Camera',
    description: 'Run local YOLO26 detection on selected webcam frames.',
    icon: Camera, insight: 'Start the camera explicitly. Only snapshots you capture are saved.',
  },
]

function StatusLabel({ status }: { status: CapabilityStatus | 'unknown' }) {
  return <span className={`module-status module-status-${status}`}>
    <span className="status-dot" />{status === 'unknown' ? 'Unknown' : status}
  </span>
}

function Workstation() {
  const { moduleId } = useParams()
  const navigate = useNavigate()
  const current = modules.find((item) => item.id === moduleId) ?? modules[0]
  const liveCamera = useLiveCamera(current.id === 'live_camera')
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
  const [selectedCaptionId, setSelectedCaptionId] = useState<string | null>(null)
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null)
  const [showRegions, setShowRegions] = useState(true)
  const [displayConfidence, setDisplayConfidence] = useState(0)
  const [excludedClasses, setExcludedClasses] = useState<string[]>([])
  const [showBoxes, setShowBoxes] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [showConfidence, setShowConfidence] = useState(true)
  const [inferenceParameters, setInferenceParameters] = useState<DetectionParameters>({ confidence: 0.25, iou: 0.45, image_size: 640, max_detections: 100 })
  const [inferenceEdited, setInferenceEdited] = useState(false)
  const [videoParameters, setVideoParameters] = useState<VideoParameters>({ detection_fps: 2, caption_interval_seconds: 10, generate_captions: true, track_objects: true, detection: { confidence: 0.25, iou: 0.45, image_size: 640, max_detections: 100 } })
  const [selectedVideoAnalysisId, setSelectedVideoAnalysisId] = useState<string | null>(null)
  const [activeVideoJobId, setActiveVideoJobId] = useState<string | null>(null)
  const [currentVideoMs, setCurrentVideoMs] = useState(0)
  const [videoSeekRequest, setVideoSeekRequest] = useState<{ ms: number; nonce: number } | null>(null)
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null)
  const [videoConfidence, setVideoConfidence] = useState(0)
  const [excludedVideoClasses, setExcludedVideoClasses] = useState<string[]>([])
  const [showVideoBoxes, setShowVideoBoxes] = useState(true)
  const [showVideoCaptions, setShowVideoCaptions] = useState(true)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const currentCapability = capabilities.data?.find((item) => item.id === current.id)
  const apiState = health.isPending ? 'checking' : health.isError ? 'disconnected' : 'connected'
  const CurrentIcon = current.icon
  const assets = media.data ?? []
  const activeAsset = assets.find((asset) => asset.media_id === activeMediaId) ?? assets[0] ?? null
  const videoMediaId = current.id !== 'live_camera' && activeAsset?.media_type === 'video' ? activeAsset.media_id : null
  const videoAnalysesQuery = useQuery({ queryKey: ['video-analyses', videoMediaId], queryFn: () => listVideoAnalyses(videoMediaId!), enabled: !!videoMediaId && health.isSuccess, refetchInterval: 2000 })
  const videoAnalyses = videoAnalysesQuery.data ?? []
  const videoAnalysis = videoAnalyses.find(item => item.analysis_id === selectedVideoAnalysisId) ?? videoAnalyses[0] ?? null
  const videoJobId = activeVideoJobId ?? videoAnalysis?.job_id ?? null
  const videoJobQuery = useQuery({ queryKey: ['video-job', videoJobId], queryFn: () => getVideoJob(videoJobId!), enabled: !!videoJobId && health.isSuccess, refetchInterval: query => query.state.data && activeJob(query.state.data.status) ? 1000 : false })
  const videoJob = videoJobQuery.data ?? null
  const runVideo = useMutation({ mutationFn: () => startVideoAnalysis(videoMediaId!, videoParameters), onSuccess: job => { setSelectedVideoAnalysisId(job.analysis_id); setActiveVideoJobId(job.job_id); void queryClient.invalidateQueries({ queryKey: ['video-analyses', videoMediaId] }) } })
  const videoBucket = Math.floor(currentVideoMs / 10000)
  const videoFramesQuery = useQuery({ queryKey: ['video-frames', videoAnalysis?.analysis_id, videoBucket], queryFn: () => getVideoFrames(videoAnalysis!.analysis_id, Math.max(0, videoBucket * 10000 - 1000), (videoBucket + 1) * 10000 + 1000), enabled: !!videoAnalysis && health.isSuccess, refetchInterval: videoJob && activeJob(videoJob.status) ? 3000 : false })
  const videoTimelineQuery = useQuery({ queryKey: ['video-timeline', videoAnalysis?.analysis_id], queryFn: () => getVideoTimeline(videoAnalysis!.analysis_id), enabled: !!videoAnalysis && health.isSuccess, refetchInterval: videoJob && activeJob(videoJob.status) ? 3000 : false })
  const videoTracksQuery = useQuery({ queryKey: ['video-tracks', videoAnalysis?.analysis_id], queryFn: () => getVideoTracks(videoAnalysis!.analysis_id), enabled: !!videoAnalysis && health.isSuccess, refetchInterval: videoJob && activeJob(videoJob.status) ? 3000 : false })
  const videoCaptionsQuery = useQuery({ queryKey: ['video-captions', videoAnalysis?.analysis_id], queryFn: () => getVideoCaptions(videoAnalysis!.analysis_id), enabled: !!videoAnalysis && health.isSuccess, refetchInterval: videoJob && activeJob(videoJob.status) ? 3000 : false })
  const videoConversationsQuery = useQuery({ queryKey: ['vqa-conversations', videoMediaId], queryFn: () => listConversations(videoMediaId!), enabled: !!videoMediaId && health.isSuccess })
  const currentVideoFrame = closestAnalyzedFrame(videoFramesQuery.data ?? [], currentVideoMs, videoAnalysis?.parameters.detection_fps ?? 2)
  const videoMarkers: TimestampedAnalysisResult[] = useMemo(() => [
    ...(videoTimelineQuery.data ?? []).map(item => ({ timestampMs: item.timestamp_ms, kind: item.object_count > 0 ? 'detection' as const : 'coverage' as const, title: `${item.object_count} objects at ${(item.timestamp_ms / 1000).toFixed(2)}s` })),
    ...(videoTracksQuery.data ?? []).map(item => ({ timestampMs: item.first_timestamp_ms, kind: 'track' as const, title: `Track #${item.track_id} first sampled at ${(item.first_timestamp_ms / 1000).toFixed(2)}s` })),
    ...(videoCaptionsQuery.data ?? []).map(item => ({ timestampMs: item.timestamp_ms, kind: 'caption' as const, title: `Caption at ${(item.timestamp_ms / 1000).toFixed(2)}s` })),
    ...(videoConversationsQuery.data ?? []).flatMap(item => item.messages.filter(message => message.role === 'assistant').flatMap(message => (message.frame_timestamps_ms ?? []).map(ms => ({ timestampMs: ms, kind: 'vqa' as const, title: `VQA examined frame at ${(ms / 1000).toFixed(2)}s` })))),
    ...(videoAnalysis && ['failed', 'interrupted'].includes(videoAnalysis.status) ? [{ timestampMs: videoAnalysis.coverage_end_ms, kind: 'failure' as const, title: `Analysis ${videoAnalysis.status} at ${(videoAnalysis.coverage_end_ms / 1000).toFixed(2)}s` }] : []),
  ], [videoTimelineQuery.data, videoTracksQuery.data, videoCaptionsQuery.data, videoConversationsQuery.data, videoAnalysis])
  const seekVideo = useCallback((ms: number) => { setVideoSeekRequest(previous => ({ ms, nonce: (previous?.nonce ?? 0) + 1 })); setCurrentVideoMs(ms) }, [])
  const refreshVideoCaptions = useCallback(() => { void queryClient.invalidateQueries({ queryKey: ['video-captions', videoAnalysis?.analysis_id] }) }, [queryClient, videoAnalysis?.analysis_id])
  const refreshVideoConversations = useCallback(() => { void queryClient.invalidateQueries({ queryKey: ['vqa-conversations', videoMediaId] }) }, [queryClient, videoMediaId])
  const detectionModule = current.id === 'analysis' || current.id === 'objects'
  const imageForAnalysis = detectionModule && activeAsset?.media_type === 'image' ? activeAsset : null
  const imageForCaption = (current.id === 'captioning' || current.id === 'objects') && activeAsset?.media_type === 'image' ? activeAsset : null
  const captionModel = useQuery({ queryKey: ['caption-model'], queryFn: getCaptionModel, enabled: health.isSuccess && (current.id === 'captioning' || current.id === 'objects'), refetchInterval: 15000 })
  const captionsQuery = useQuery({ queryKey: ['captions', imageForCaption?.media_id], queryFn: () => listCaptions(imageForCaption!.media_id), enabled: !!imageForCaption && health.isSuccess })
  const captions = captionsQuery.data ?? []
  const selectableCaptions = captions.filter((item) => item.task !== 'selected_object')
  const selectedCaption = selectableCaptions.find((item) => item.analysis_id === selectedCaptionId) ?? selectableCaptions[0] ?? null
  const latestDense = captions.find((item) => item.task === 'dense') ?? null
  const visibleRegions = current.id === 'captioning' && selectedCaption?.task === 'dense' ? selectedCaption.regions : current.id === 'objects' ? latestDense?.regions ?? [] : []
  const regionOverlays = showRegions ? visibleRegions.map((item) => ({ id: item.id, label: item.description.length > 25 ? `${item.description.slice(0, 25)}…` : item.description,
    box: { x1: item.bounding_box.x, y1: item.bounding_box.y, x2: item.bounding_box.x + item.bounding_box.width, y2: item.bounding_box.y + item.bounding_box.height } })) : []
  const saveCaption = (record: CaptionRecord) => { queryClient.setQueryData<CaptionRecord[]>(['captions', record.media_id], (current) => [record, ...(current ?? [])]);
    setSelectedCaptionId(record.analysis_id); setSelectedRegionId(null); void queryClient.invalidateQueries({ queryKey: ['caption-model'] }); void queryClient.invalidateQueries({ queryKey: ['capabilities'] }) }
  const runCaption = useMutation({ mutationFn: (mode: CaptionMode) => generateCaption(imageForCaption!.media_id, mode), onSuccess: saveCaption })
  const runDense = useMutation({ mutationFn: () => generateDenseRegions(imageForCaption!.media_id), onSuccess: saveCaption })
  const runDescribe = useMutation({ mutationFn: () => describeObject(imageForCaption!.media_id, analysis!.analysis_id, selectedObjectId!), onSuccess: (record) => {
    queryClient.setQueryData<CaptionRecord[]>(['captions', record.media_id], (current) => [record, ...(current ?? [])]);
    void queryClient.invalidateQueries({ queryKey: ['capabilities'] })
  } })
  const modelQuery = useQuery({ queryKey: ['vision-models'], queryFn: getModels, enabled: health.isSuccess && detectionModule, refetchInterval: 15000 })
  useEffect(() => {
    const defaults = modelQuery.data?.[0]?.defaults
    if (defaults && !inferenceEdited) setInferenceParameters(defaults)
  }, [modelQuery.data, inferenceEdited])
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
  const savedDescription = captions.find((item) => item.task === 'selected_object' && item.detection_analysis_id === analysis?.analysis_id && item.detection_id === selectedObjectId)
  const visibleObjects = (analysis?.detections ?? []).filter((item) => item.confidence >= displayConfidence && !excludedClasses.includes(item.label))
  const overlays = detectionModule && showBoxes ? visibleObjects.map((item) => ({ id: item.id, classId: item.class_id,
    label: item.label, confidence: item.confidence, box: { x1: item.bounding_box.x, y1: item.bounding_box.y,
      x2: item.bounding_box.x + item.bounding_box.width, y2: item.bounding_box.y + item.bounding_box.height } })) : []

  function resetDisplay() { setDisplayConfidence(0); setExcludedClasses([]); setShowBoxes(true); setShowLabels(true); setShowConfidence(true) }

  function onUploaded(asset: MediaAsset) {
    setUploadNotice(`${asset.original_filename} uploaded and ready.`)
    selectMedia(asset.media_id)
    runAnalysis.reset()
    setSelectedObjectId(null)
    setSelectedCaptionId(null); setSelectedRegionId(null)
    setSelectedVideoAnalysisId(null); setActiveVideoJobId(null); setCurrentVideoMs(0); setSelectedTrackId(null)
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
      runAnalysis.reset()
      runCaption.reset(); runDense.reset(); runDescribe.reset()
      queryClient.removeQueries({ queryKey: ['analyses', mediaId] })
      queryClient.removeQueries({ queryKey: ['captions', mediaId] })
      queryClient.removeQueries({ queryKey: ['vqa-conversations', mediaId] })
      queryClient.removeQueries({ queryKey: ['accessibility', mediaId] })
      queryClient.removeQueries({ queryKey: ['video-analyses', mediaId] })
      localStorage.removeItem(`visionlab:openai-consent:${mediaId}`)
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
          <div className="sidebar-info"><Layers3 size={16} /><span>Learning workspace</span><span className="phase-pill">PHASE 07</span></div>
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
            <span className="phase-badge"><span />Phase 7 live camera</span>
          </div>
        </div>

        <section className="viewer-panel" aria-labelledby="viewer-title">
          <div className="panel-toolbar">
            <div className="panel-title"><span className="panel-title-icon"><ImageIcon size={17} /></span><span id="viewer-title">{current.id === 'live_camera' ? 'Live camera' : 'Media viewer'}</span><span className="panel-tag">{current.id === 'live_camera' ? 'LIVE' : activeAsset ? activeAsset.media_type.toUpperCase() : 'NO MEDIA'}</span></div>
            <div className="viewer-actions">
              <span className="tool-label">Original media</span>
              {current.id !== 'live_camera' && activeAsset && <><span className="vertical-rule" /><MediaUploader compact disabled={!health.isSuccess} limits={limits.data} onUploaded={onUploaded} /></>}
            </div>
          </div>
          {uploadNotice && <div className="upload-success-banner" role="status"><Check size={15} /><span>{uploadNotice}</span><button type="button" onClick={() => setUploadNotice('')} aria-label="Dismiss upload message">×</button></div>}
          <div className={`viewer-stage ${activeAsset || current.id === 'live_camera' ? 'has-media' : ''}`}>
            {current.id === 'live_camera' ? <LiveCameraStage camera={liveCamera} onSnapshot={asset => { onUploaded(asset); navigate('/workspace/analysis') }} /> : activeAsset ? <MediaViewer asset={activeAsset} detections={overlays} regions={regionOverlays} selectedId={selectedObjectId} selectedRegionId={selectedRegionId} onSelect={setSelectedObjectId} onSelectRegion={current.id === 'captioning' ? setSelectedRegionId : undefined} showLabels={showLabels} showConfidence={showConfidence} videoFrames={videoFramesQuery.data ?? []} videoCaptions={videoCaptionsQuery.data ?? []} videoMarkers={videoMarkers} videoFps={videoAnalysis?.parameters.detection_fps} selectedTrackId={selectedTrackId} videoConfidence={videoConfidence} excludedVideoClasses={excludedVideoClasses} showVideoBoxes={showVideoBoxes} showVideoCaptions={showVideoCaptions} seekRequest={videoSeekRequest} onVideoTimeChange={setCurrentVideoMs} /> : health.isPending || media.isPending && health.isSuccess ?
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
          <div className="viewer-footer"><span><span className="footer-dot" />{current.id === 'live_camera' ? `Camera ${liveCamera.status}` : activeAsset ? activeAsset.original_filename : 'Awaiting media'}</span><span>{current.id === 'live_camera' ? 'Live frames stay local unless you save a snapshot' : activeAsset ? `${activeAsset.width} × ${activeAsset.height} · ${formatBytes(activeAsset.file_size_bytes)}` : 'Overlays appear when providers are enabled'}</span></div>
        </section>

        {videoMediaId && <><VideoAnalysisControls analyses={videoAnalyses} selected={videoAnalysis} job={videoJob} parameters={videoParameters} onParameters={setVideoParameters} onAnalyze={() => runVideo.mutate()} onSelect={id => { setSelectedVideoAnalysisId(id); setActiveVideoJobId(null); setSelectedTrackId(null) }} loading={runVideo.isPending} error={runVideo.isError ? mediaErrorMessage(runVideo.error) : videoAnalysesQuery.isError ? mediaErrorMessage(videoAnalysesQuery.error) : ''} /><label className="analysis-checks"><input type="checkbox" checked={showVideoCaptions} onChange={event => setShowVideoCaptions(event.target.checked)} /> Caption overlay</label></>}

        {detectionModule && !videoMediaId && <section className="analysis-run-panel" aria-label="Image detection controls">
          <div><strong>YOLO26 Nano · Image detection</strong><span>{imageForAnalysis ? `Model ${modelQuery.data?.[0]?.state.replace('_', ' ') ?? 'checking'} · ${analyses.length} saved run${analyses.length === 1 ? '' : 's'}` : 'Select or upload an image to begin.'}</span></div>
          {imageForAnalysis && <>
            <div className="inference-fields"><label>Inference confidence <input aria-label="Inference confidence" type="number" min="0.01" max="1" step="0.01" value={inferenceParameters.confidence} onChange={(event) => { setInferenceEdited(true); setInferenceParameters({ ...inferenceParameters, confidence: Number(event.target.value) }) }} /></label><label>IoU <input aria-label="Inference IoU" type="number" min="0" max="1" step="0.01" value={inferenceParameters.iou} onChange={(event) => { setInferenceEdited(true); setInferenceParameters({ ...inferenceParameters, iou: Number(event.target.value) }) }} /></label></div>
            <Button type="button" onClick={() => runAnalysis.mutate()} disabled={runAnalysis.isPending || inferenceParameters.confidence <= 0 || inferenceParameters.confidence > 1 || inferenceParameters.iou < 0 || inferenceParameters.iou > 1}>{runAnalysis.isPending ? 'Analyzing…' : analysis ? 'Re-run Analysis' : 'Analyze Image'}</Button>
            {analyses.length > 1 && <label className="analysis-run-select">Saved run <select aria-label="Saved analysis" value={analysis?.analysis_id} onChange={(event) => { selectAnalysis(event.target.value); setSelectedObjectId(null) }}>{analyses.map((item) => <option key={item.analysis_id} value={item.analysis_id}>{new Date(item.created_at).toLocaleString()} · {item.status}</option>)}</select></label>}
            {current.id === 'objects' && latestDense && <label className="analysis-checks"><input type="checkbox" checked={showRegions} onChange={(event) => setShowRegions(event.target.checked)} /> Show Florence regions</label>}
          </>}
        </section>}

        {current.id !== 'live_camera' && <MediaLibrary assets={assets} activeId={activeAsset?.media_id ?? null} onSelect={(id) => { selectMedia(id); runAnalysis.reset(); runCaption.reset(); runDense.reset(); runDescribe.reset(); setSelectedObjectId(null); setSelectedCaptionId(null); setSelectedRegionId(null); setSelectedVideoAnalysisId(null); setActiveVideoJobId(null); setCurrentVideoMs(0); setSelectedTrackId(null); resetDisplay() }} loading={health.isPending || (media.isPending && health.isSuccess)} error={media.isError || health.isError} onRetry={() => { void health.refetch(); void media.refetch() }} />}

        <section className="foundation-strip" aria-label="Phase seven progress">
          <div className="foundation-icon"><Check size={18} /></div>
          <div><strong>Image, video, and live camera workspace active</strong><span>Analyze media with local models and save camera snapshots explicitly.</span></div>
          <span className="foundation-index">07 / 08</span>
        </section>
      </main>

      <aside className="inspector" aria-label="AI results inspector">
        <div className="inspector-header"><div><span className="inspector-overline">INTELLIGENCE PANEL</span><h2>AI Inspector</h2></div><Sparkles size={19} /></div>
        <div className="inspector-tabs"><span className="inspector-tab active">Overview</span></div>
        <div className="inspector-content">
          {current.id === 'live_camera' ? <LiveCameraInspector camera={liveCamera} /> : videoMediaId ? current.id === 'analysis' || current.id === 'objects' ? <VideoDetectionInspector analysis={videoAnalysis} frame={currentVideoFrame} tracks={videoTracksQuery.data ?? []} currentMs={currentVideoMs} confidence={videoConfidence} onConfidence={setVideoConfidence} excludedClasses={excludedVideoClasses} onExcludedClasses={setExcludedVideoClasses} selectedTrackId={selectedTrackId} onSelectedTrack={setSelectedTrackId} showBoxes={showVideoBoxes} onShowBoxes={setShowVideoBoxes} showLabels={showLabels} onShowLabels={setShowLabels} showConfidence={showConfidence} onShowConfidence={setShowConfidence} onSeek={seekVideo} /> : current.id === 'captioning' ? <VideoCaptionInspector mediaId={videoMediaId} analysis={videoAnalysis} captions={videoCaptionsQuery.data ?? []} currentMs={currentVideoMs} onSeek={seekVideo} onRefresh={refreshVideoCaptions} /> : current.id === 'vqa' ? <VideoVQAInspector mediaId={videoMediaId} currentMs={currentVideoMs} durationMs={activeAsset?.duration_ms ?? 0} onSeek={seekVideo} onRefresh={refreshVideoConversations} /> : <VideoCaptionInspector mediaId={videoMediaId} analysis={videoAnalysis} captions={videoCaptionsQuery.data ?? []} currentMs={currentVideoMs} onSeek={seekVideo} onRefresh={refreshVideoCaptions} accessible /> : detectionModule ? <DetectionInspector analysis={analysis} model={modelQuery.data?.[0] ?? null} loading={runAnalysis.isPending || analysesQuery.isPending && !!imageForAnalysis} error={runAnalysis.isError ? mediaErrorMessage(runAnalysis.error) : analysesQuery.isError ? mediaErrorMessage(analysesQuery.error) : ''} visible={visibleObjects} selectedId={selectedObjectId} onSelect={setSelectedObjectId} displayConfidence={displayConfidence} onDisplayConfidence={setDisplayConfidence} selectedClasses={excludedClasses} onSelectedClasses={setExcludedClasses} showBoxes={showBoxes} onShowBoxes={setShowBoxes} showLabels={showLabels} onShowLabels={setShowLabels} showConfidence={showConfidence} onShowConfidence={setShowConfidence} onReset={resetDisplay} onDescribe={current.id === 'objects' && selectedObjectId && analysis ? () => runDescribe.mutate() : undefined} describeLoading={runDescribe.isPending} describeError={runDescribe.isError ? mediaErrorMessage(runDescribe.error) : ''} description={savedDescription?.text ? { text: savedDescription.text, model: savedDescription.model.checkpoint, duration: savedDescription.inference_ms } : null} /> : current.id === 'captioning' ? <CaptionInspector imageReady={!!imageForCaption} model={captionModel.data ?? null} records={selectableCaptions} selected={selectedCaption} selectedRegionId={selectedRegionId} showRegions={showRegions} onShowRegions={setShowRegions} onSelectRecord={(id) => { setSelectedCaptionId(id); setSelectedRegionId(null) }} onSelectRegion={setSelectedRegionId} onGenerate={(mode) => runCaption.mutate(mode)} onDense={() => runDense.mutate()} loading={runCaption.isPending || runDense.isPending} historyLoading={captionsQuery.isPending && !!imageForCaption} error={runCaption.isError ? mediaErrorMessage(runCaption.error) : runDense.isError ? mediaErrorMessage(runDense.error) : captionsQuery.isError ? mediaErrorMessage(captionsQuery.error) : ''} /> : current.id === 'vqa' ? <VQAInspector mediaId={activeAsset?.media_id ?? null} isVideo={false} /> : current.id === 'accessibility' ? <AccessibilityInspector mediaId={activeAsset?.media_id ?? null} isVideo={false} /> : <div className="inspector-empty"><div className="inspector-empty-icon"><WandSparkles size={22} /></div><strong>No AI analysis yet</strong><p>This capability is planned for a later phase.</p></div>}
          {current.id !== 'live_camera' && <MediaInspector asset={activeAsset} onDelete={(id) => void onDelete(id)} deleting={deleting} error={deleteError} />}
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

