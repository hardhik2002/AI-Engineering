import { useRef, useState } from 'react'
import { FileImage, Film, RotateCcw, Upload, X } from 'lucide-react'
import { useDropzone, type FileError } from 'react-dropzone'
import { Button } from '@/components/ui/button'
import { formatBytes, mediaErrorMessage, uploadMedia } from '@/lib/media'
import type { MediaAsset } from '@/types/media'

const imageLimit = 20 * 1024 * 1024
const videoLimit = 250 * 1024 * 1024
const accept = {
  'image/jpeg': ['.jpg', '.jpeg'], 'image/png': ['.png'], 'image/webp': ['.webp'],
  'video/mp4': ['.mp4'], 'video/webm': ['.webm'],
}

interface Props { compact?: boolean; disabled?: boolean; onUploaded: (asset: MediaAsset) => void }

export function MediaUploader({ compact = false, disabled = false, onUploaded }: Props) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<'idle' | 'uploading' | 'success' | 'cancelled' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const controller = useRef<AbortController | null>(null)

  async function startUpload(file: File) {
    controller.current?.abort()
    const nextController = new AbortController()
    controller.current = nextController
    setSelectedFile(file)
    setProgress(0)
    setMessage('')
    setStatus('uploading')
    try {
      const asset = await uploadMedia(file, nextController.signal, setProgress)
      setStatus('success')
      setMessage(`${asset.original_filename} is ready.`)
      onUploaded(asset)
    } catch (error) {
      setStatus(nextController.signal.aborted ? 'cancelled' : 'error')
      setMessage(nextController.signal.aborted ? 'Upload cancelled.' : mediaErrorMessage(error))
    } finally {
      if (controller.current === nextController) controller.current = null
    }
  }

  function validateFile(file: File): FileError | null {
    const maximum = file.type.startsWith('video/') ? videoLimit : imageLimit
    return file.size > maximum ? { code: 'file-too-large', message: `File exceeds ${formatBytes(maximum)}.` } : null
  }

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    accept, multiple: false, noClick: true, disabled: disabled || status === 'uploading', validator: validateFile,
    onDropAccepted: ([file]) => { if (file) void startUpload(file) },
    onDropRejected: ([rejection]) => {
      setStatus('error')
      setMessage(rejection?.errors[0]?.message || 'Unsupported file. Use JPEG, PNG, WebP, MP4 or WebM.')
    },
  })

  return <div {...getRootProps({ className: compact ? 'uploader-compact' : `upload-zone ${isDragActive ? 'drag-active' : ''}` })}>
    <input {...getInputProps()} aria-label="Choose an image or video" />
    {!compact && <>
      <span className="upload-art"><Upload size={25} strokeWidth={1.6} /></span>
      <span className="upload-eyebrow">YOUR CANVAS IS READY</span>
      <h2>{isDragActive ? 'Drop your media here' : 'Add an image or video'}</h2>
      <p>Drop a file here or browse your device. Your media is saved locally and can be reopened later.</p>
      <div className="upload-formats"><span><FileImage size={14} /> JPEG · PNG · WebP</span><span><Film size={14} /> MP4 · WebM</span></div>
    </>}
    <Button type="button" onClick={open} disabled={disabled || status === 'uploading'} variant={compact ? 'secondary' : 'default'} size={compact ? 'small' : 'default'}>
      <Upload size={15} />{compact ? 'Add media' : 'Browse files'}
    </Button>
    {!compact && <span className="upload-limits">Images up to 20 MB · Videos up to 250 MB / 10 min</span>}
    {status !== 'idle' && <div className={`upload-feedback upload-${status}`} role="status">
      {selectedFile && <span className="upload-name">{selectedFile.name} · {formatBytes(selectedFile.size)}</span>}
      {status === 'uploading' && <><div className="upload-progress"><span style={{ width: `${progress}%` }} /></div><span>{progress}%</span><Button type="button" variant="ghost" size="icon" onClick={() => controller.current?.abort()} aria-label="Cancel upload"><X size={15} /></Button></>}
      {status !== 'uploading' && <span className="upload-message">{message}</span>}
      {(status === 'error' || status === 'cancelled') && selectedFile && <Button type="button" variant="ghost" size="small" disabled={disabled} onClick={() => void startUpload(selectedFile)}><RotateCcw size={13} />Retry</Button>}
    </div>}
  </div>
}
