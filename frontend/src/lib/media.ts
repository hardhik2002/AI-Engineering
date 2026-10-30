import axios, { isAxiosError } from 'axios'
import { api } from '@/lib/api'
import type { ApiError, MediaAsset, MediaLimits } from '@/types/media'

const baseURL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5200').replace(/\/$/, '')

export function mediaContentUrl(mediaId: string) {
  return `${baseURL}/api/v1/media/${encodeURIComponent(mediaId)}/content`
}

export function mediaThumbnailUrl(mediaId: string) {
  return `${baseURL}/api/v1/media/${encodeURIComponent(mediaId)}/thumbnail`
}

export async function listMedia(): Promise<MediaAsset[]> {
  const { data } = await api.get<MediaAsset[]>('/api/v1/media')
  return data
}

export async function getMediaLimits(): Promise<MediaLimits> {
  const { data } = await api.get<MediaLimits>('/api/v1/media/limits')
  return data
}

export async function uploadMedia(file: File, signal: AbortSignal, onProgress: (percent: number) => void): Promise<MediaAsset> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<MediaAsset>('/api/v1/media/upload', form, {
    signal,
    timeout: 0,
    onUploadProgress: (event) => {
      if (event.total) onProgress(Math.min(99, Math.round(event.loaded / event.total * 100)))
    },
  })
  onProgress(100)
  return data
}

export async function deleteMedia(mediaId: string): Promise<void> {
  await api.delete(`/api/v1/media/${encodeURIComponent(mediaId)}`)
}

export function mediaErrorMessage(error: unknown): string {
  if (axios.isCancel(error)) return 'Upload cancelled.'
  if (isAxiosError<ApiError>(error)) {
    const message = error.response?.data?.error?.message || 'Could not reach the media service.'
    const requestId = error.response?.headers?.['x-request-id']
    return typeof requestId === 'string' && requestId ? `${message} Reference ID: ${requestId}` : message
  }
  return error instanceof Error ? error.message : 'Something went wrong.'
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return '0:00'
  const total = Math.max(0, Math.floor(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

