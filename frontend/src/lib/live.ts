const baseURL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5200').replace(/\/$/, '')

export function liveSocketUrl(): string {
  return `${baseURL.replace(/^http/i, 'ws')}/ws/v1/live`
}

export async function encodeLiveFrame(metadata: {
  session_id: string; frame_id: string; captured_at_ms: number
  source_width: number; source_height: number
}, blob: Blob): Promise<ArrayBuffer> {
  const header = new TextEncoder().encode(JSON.stringify({
    type: 'frame.submitted', ...metadata, encoded_format: 'jpeg',
  }))
  if (header.length > 1024) throw new Error('Camera metadata exceeds protocol limit.')
  const image = new Uint8Array(await blob.arrayBuffer())
  const packet = new Uint8Array(7 + header.length + image.length)
  packet.set([0x56, 0x4c, 0x31])
  new DataView(packet.buffer).setUint32(3, header.length)
  packet.set(header, 7)
  packet.set(image, 7 + header.length)
  return packet.buffer
}

export function cameraError(error: unknown): string {
  if (!(error instanceof DOMException)) return error instanceof Error ? error.message : 'Camera could not start.'
  switch (error.name) {
    case 'NotAllowedError': return 'Camera permission was denied. Allow camera access in browser settings.'
    case 'NotFoundError': return 'No camera was found. Connect a camera and retry.'
    case 'NotReadableError': return 'The camera is busy or unavailable to this browser.'
    case 'OverconstrainedError': return 'This camera cannot provide the selected resolution. Try another setting.'
    default: return 'Camera could not start. Check browser permissions and device availability.'
  }
}
