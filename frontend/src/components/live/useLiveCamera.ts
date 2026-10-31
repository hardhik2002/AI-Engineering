import { useCallback, useEffect, useRef, useState } from 'react'
import { cameraError, encodeLiveFrame, liveSocketUrl } from '@/lib/live'
import { uploadMedia } from '@/lib/media'
import type { MediaAsset } from '@/types/media'
import type { LiveMessage, LiveResult, LiveStarted } from '@/types/live'

type CameraStatus = 'stopped' | 'requesting' | 'connecting' | 'running' | 'disconnected' | 'error'
type Resolution = '320x240' | '640x480'
const MAX_RESULT_AGE_MS = 5000

export function useLiveCamera(enabled: boolean) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const activeVideoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const socketErrorRef = useRef('')
  const sessionRef = useRef<LiveStarted | null>(null)
  const inFlightRef = useRef<string | null>(null)
  const inFlightAtRef = useRef(0)
  const frameCallbackRef = useRef<number | null>(null)
  const intervalRef = useRef<number | null>(null)
  const generationRef = useRef(0)
  const activeRef = useRef(false)
  const lastCaptureRef = useRef(-Infinity)
  const processedTimesRef = useRef<number[]>([])
  const previewTimesRef = useRef<number[]>([])
  const lastPreviewUpdateRef = useRef(0)
  const [status, setStatus] = useState<CameraStatus>('stopped')
  const [error, setError] = useState('')
  const [result, setResult] = useState<LiveResult | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [activeSessions, setActiveSessions] = useState(0)
  const [deviceId, setDeviceId] = useState('')
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user')
  const [resolution, setResolution] = useState<Resolution>('640x480')
  const [analysisFps, setAnalysisFps] = useState(2)
  const [mirror, setMirror] = useState(true)
  const [showBoxes, setShowBoxes] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [showConfidence, setShowConfidence] = useState(true)
  const [displayConfidence, setDisplayConfidence] = useState(0)
  const [excludedClasses, setExcludedClasses] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [metrics, setMetrics] = useState({ captured: 0, sent: 0, processed: 0, dropped: 0,
    previewFps: null as number | null, inferenceFps: null as number | null,
    inferenceMs: null as number | null,
    roundTripMs: null as number | null })
  const fpsRef = useRef(analysisFps)
  fpsRef.current = analysisFps
  const resolutionRef = useRef(resolution)
  resolutionRef.current = resolution

  const stop = useCallback(() => {
    generationRef.current += 1
    activeRef.current = false
    const video = videoRef.current ?? activeVideoRef.current
    if (video && frameCallbackRef.current !== null && 'cancelVideoFrameCallback' in video) {
      video.cancelVideoFrameCallback(frameCallbackRef.current)
    }
    frameCallbackRef.current = null
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current)
    intervalRef.current = null
    const socket = socketRef.current
    socketRef.current = null
    if (socket) {
      if (socket.readyState === 1) socket.send(JSON.stringify({ type: 'session.stop' }))
      socket.close()
    }
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
    if (video) { video.pause(); video.srcObject = null }
    activeVideoRef.current = null
    if (canvasRef.current) { canvasRef.current.width = 0; canvasRef.current.height = 0 }
    sessionRef.current = null
    setActiveSessions(0)
    inFlightRef.current = null
    setResult(null); setSelectedId(null); setStatus('stopped')
  }, [])

  const captureFrame = useCallback(() => {
    const video = videoRef.current
    const socket = socketRef.current
    const session = sessionRef.current
    if (!activeRef.current || !video || !socket || socket.readyState !== 1 || !session) return
    const now = performance.now()
    if (now - lastCaptureRef.current < 1000 / Math.min(fpsRef.current, session.max_fps)) return
    lastCaptureRef.current = now
    if (result && now - result.captured_at_ms > MAX_RESULT_AGE_MS) {
      setResult(null); setSelectedId(null)
    }
    if (inFlightRef.current || socket.bufferedAmount > session.max_frame_bytes) {
      setMetrics(previous => ({ ...previous, dropped: previous.dropped + 1 }))
      if (inFlightRef.current && now - inFlightAtRef.current > 15000) socket.close()
      return
    }
    if (!video.videoWidth || !video.videoHeight) return
    const [desiredWidth, desiredHeight] = resolutionRef.current.split('x').map(Number)
    const scale = Math.min(1, desiredWidth / video.videoWidth, desiredHeight / video.videoHeight,
      session.max_width / video.videoWidth, session.max_height / video.videoHeight)
    const width = Math.max(1, Math.round(video.videoWidth * scale))
    const height = Math.max(1, Math.round(video.videoHeight * scale))
    const canvas = canvasRef.current ?? document.createElement('canvas')
    canvasRef.current = canvas
    canvas.width = width; canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) return
    context.drawImage(video, 0, 0, width, height)
    setMetrics(previous => ({ ...previous, captured: previous.captured + 1 }))
    const frameId = crypto.randomUUID()
    const generation = generationRef.current
    inFlightRef.current = frameId
    inFlightAtRef.current = now
    canvas.toBlob(blob => {
      if (generation !== generationRef.current || inFlightRef.current !== frameId) return
      if (!blob || blob.size > session.max_frame_bytes) {
        inFlightRef.current = null
        setMetrics(previous => ({ ...previous, dropped: previous.dropped + 1 }))
        return
      }
      void encodeLiveFrame({ session_id: session.session_id, frame_id: frameId,
        captured_at_ms: now, source_width: width, source_height: height }, blob)
        .then(packet => {
          if (generation !== generationRef.current || socket.readyState !== 1 ||
            inFlightRef.current !== frameId || socket.bufferedAmount > session.max_frame_bytes) {
            inFlightRef.current = null
            setMetrics(previous => ({ ...previous, dropped: previous.dropped + 1 }))
            return
          }
          socket.send(packet)
          setMetrics(previous => ({ ...previous, sent: previous.sent + 1 }))
        })
        .catch(() => { inFlightRef.current = null; setMetrics(previous => ({ ...previous, dropped: previous.dropped + 1 })) })
    }, 'image/jpeg', 0.72)
  }, [result])
  const captureRef = useRef(captureFrame)
  captureRef.current = captureFrame

  const start = useCallback(async () => {
    if (activeRef.current) return
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('error'); setError('This browser does not support camera capture in this context.')
      return
    }
    activeRef.current = true
    const generation = ++generationRef.current
    setStatus('requesting'); setError(''); setResult(null)
    socketErrorRef.current = ''
    setMetrics({ captured: 0, sent: 0, processed: 0, dropped: 0,
      previewFps: null, inferenceFps: null, inferenceMs: null, roundTripMs: null })
    processedTimesRef.current = []
    previewTimesRef.current = []
    lastCaptureRef.current = -Infinity
    try {
      const [width, height] = resolution.split('x').map(Number)
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: width }, height: { ideal: height },
          ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: facingMode } }) },
        audio: false,
      })
      if (generation !== generationRef.current) { stream.getTracks().forEach(track => track.stop()); return }
      streamRef.current = stream
      const video = videoRef.current
      if (!video) { stop(); return }
      activeVideoRef.current = video
      video.srcObject = stream
      stream.getVideoTracks().forEach(track => { track.onended = () => {
        if (generation === generationRef.current) {
          stop(); setStatus('disconnected'); setError('Camera disconnected. Reconnect it and start again.')
        }
      } })
      await video.play()
      if (generation !== generationRef.current) return
      try { setDevices((await navigator.mediaDevices.enumerateDevices()).filter(item => item.kind === 'videoinput')) }
      catch { setDevices([]) }
      setStatus('connecting')
      const socket = new WebSocket(liveSocketUrl())
      socket.binaryType = 'arraybuffer'
      socketRef.current = socket
      socket.onmessage = event => {
        if (generation !== generationRef.current) return
        let message: LiveMessage
        try { message = JSON.parse(event.data) as LiveMessage }
        catch { return }
        if (message.type === 'session.started') {
          if (message.protocol_version !== 1) { socket.close(); return }
          sessionRef.current = message
          setActiveSessions(message.active_sessions)
          setStatus('running')
          if ('requestVideoFrameCallback' in video) {
            const tick = (now: number) => {
              if (generation !== generationRef.current) return
              previewTimesRef.current = [...previewTimesRef.current.filter(item => now - item <= 3000), now]
              const times = previewTimesRef.current
              if (times.length > 1 && now - times[0] > 0 &&
                  now - lastPreviewUpdateRef.current >= 500) {
                lastPreviewUpdateRef.current = now
                setMetrics(previous => ({ ...previous,
                  previewFps: (times.length - 1) * 1000 / (now - times[0]) }))
              }
              captureRef.current()
              frameCallbackRef.current = video.requestVideoFrameCallback(tick)
            }
            frameCallbackRef.current = video.requestVideoFrameCallback(tick)
          } else {
            intervalRef.current = window.setInterval(() => captureRef.current(), 100)
          }
        } else if (message.type === 'frame.result') {
          if (message.session_id !== sessionRef.current?.session_id ||
            message.frame_id !== inFlightRef.current) return
          inFlightRef.current = null
          const now = performance.now()
          const roundTrip = Math.max(0, now - message.captured_at_ms)
          processedTimesRef.current = [...processedTimesRef.current.filter(item => now - item <= 10000), now]
          const times = processedTimesRef.current
          const inferenceFps = times.length > 1 ?
            (times.length - 1) * 1000 / (times[times.length - 1] - times[0]) : null
          setMetrics(previous => ({ ...previous, processed: previous.processed + 1,
            inferenceMs: message.inference_ms, roundTripMs: roundTrip, inferenceFps }))
          if (roundTrip <= MAX_RESULT_AGE_MS) {
            setResult(message)
            setSelectedId(previous => message.detections.some(item => item.id === previous) ? previous : null)
          } else { setResult(null); setMetrics(previous => ({ ...previous, dropped: previous.dropped + 1 })) }
        } else if (message.type === 'frame.skipped') {
          if (message.session_id === sessionRef.current?.session_id && message.frame_id === inFlightRef.current) {
            inFlightRef.current = null
            setMetrics(previous => ({ ...previous, dropped: previous.dropped + 1 }))
          }
        } else if (message.type === 'session.error') {
          socketErrorRef.current = message.message
          setError(message.message)
          inFlightRef.current = null
        }
      }
      socket.onclose = () => {
        if (generation !== generationRef.current || !activeRef.current) return
        const message = socketErrorRef.current || 'Live connection closed. Start Camera to reconnect.'
        stop(); setStatus('disconnected'); setError(message)
      }
      socket.onerror = () => { if (generation === generationRef.current) {
        socketErrorRef.current = 'Live connection could not be established.'
        setError(socketErrorRef.current)
      } }
    } catch (caught) {
      if (generation !== generationRef.current) return
      stop(); setStatus('error'); setError(cameraError(caught))
    }
  }, [deviceId, facingMode, resolution, stop])

  useEffect(() => { if (!enabled) stop() }, [enabled, stop])
  useEffect(() => {
    if (enabled && activeRef.current) { stop(); void start() }
  }, [deviceId, facingMode, resolution, enabled, start, stop])
  useEffect(() => {
    const hide = () => { if (document.hidden) stop() }
    window.addEventListener('pagehide', stop)
    document.addEventListener('visibilitychange', hide)
    return () => { window.removeEventListener('pagehide', stop); document.removeEventListener('visibilitychange', hide); stop() }
  }, [stop])
  useEffect(() => {
    if (!result) return
    const remaining = Math.max(0, MAX_RESULT_AGE_MS - (performance.now() - result.captured_at_ms))
    const timeout = window.setTimeout(() => { setResult(null); setSelectedId(null) }, remaining)
    return () => window.clearTimeout(timeout)
  }, [result])

  const snapshot = useCallback(async (onUploaded: (asset: MediaAsset) => void) => {
    const video = videoRef.current
    if (!video || !streamRef.current || !video.videoWidth) return
    setSaving(true); setError('')
    try {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth; canvas.height = video.videoHeight
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Snapshot canvas is unavailable.')
      if (mirror) { context.translate(canvas.width, 0); context.scale(-1, 1) }
      context.drawImage(video, 0, 0)
      const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
        value => value ? resolve(value) : reject(new Error('Snapshot encoding failed.')),
        'image/jpeg', 0.9))
      const file = new File([blob], `camera-${new Date().toISOString().replace(/[:.]/g, '-')}.jpg`, { type: 'image/jpeg' })
      const asset = await uploadMedia(file, new AbortController().signal, () => {})
      onUploaded(asset)
    } catch (caught) { setError(cameraError(caught)) }
    finally { setSaving(false) }
  }, [mirror])

  return { videoRef, status, error, result, selectedId, setSelectedId, devices, deviceId,
    activeSessions,
    setDeviceId, facingMode, setFacingMode, resolution, setResolution, analysisFps,
    setAnalysisFps, mirror, setMirror, showBoxes, setShowBoxes, showLabels, setShowLabels,
    showConfidence, setShowConfidence, displayConfidence, setDisplayConfidence,
    excludedClasses, setExcludedClasses, saving, metrics, start, stop, snapshot }
}

export type LiveCameraController = ReturnType<typeof useLiveCamera>
