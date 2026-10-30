import { FileImage, Film, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatBytes, formatTime } from '@/lib/media'
import type { MediaAsset } from '@/types/media'

interface Props { asset: MediaAsset | null; onDelete: (id: string) => void; deleting: boolean; error: string }

export function MediaInspector({ asset, onDelete, deleting, error }: Props) {
  return <div className="inspector-section"><div className="section-label">ACTIVE MEDIA</div>
    {!asset ? <div className="media-info-empty">Select or upload media to see its verified details.</div> :
      <div className="media-info-card">
        <div className="media-info-title">{asset.media_type === 'image' ? <FileImage size={18} /> : <Film size={18} />}<strong title={asset.original_filename}>{asset.original_filename}</strong></div>
        <dl>
          <div><dt>Format</dt><dd>{asset.detected_mime_type}</dd></div>
          <div><dt>Resolution</dt><dd>{asset.width} × {asset.height}</dd></div>
          <div><dt>File size</dt><dd>{formatBytes(asset.file_size_bytes)}</dd></div>
          {asset.duration_ms !== null && <div><dt>Duration</dt><dd>{formatTime(asset.duration_ms / 1000)}</dd></div>}
          {asset.frame_rate !== null && <div><dt>Frame rate</dt><dd>{asset.frame_rate} fps</dd></div>}
          {asset.video_codec && <div><dt>Codec</dt><dd>{asset.video_codec}</dd></div>}
        </dl>
        {asset.playback_compatibility === 'uncertain' && <p className="compatibility-note">Browser playback for this codec may vary.</p>}
        <Button type="button" variant="ghost" size="small" disabled={deleting} onClick={() => onDelete(asset.media_id)} className="delete-media"><Trash2 size={14} />{deleting ? 'Removing…' : 'Delete media'}</Button>
        {error && <p className="media-delete-error" role="alert">{error}</p>}
      </div>}
  </div>
}
