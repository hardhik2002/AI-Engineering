import { Film, Image as ImageIcon } from 'lucide-react'
import { mediaThumbnailUrl } from '@/lib/media'
import type { MediaAsset } from '@/types/media'

interface Props {
  assets: MediaAsset[]
  activeId: string | null
  onSelect: (id: string) => void
  loading: boolean
  error: boolean
  onRetry: () => void
}

export function MediaLibrary({ assets, activeId, onSelect, loading, error, onRetry }: Props) {
  return <section className="media-library" aria-label="Recent media">
    <div className="library-heading"><div><span className="section-label">LOCAL LIBRARY</span><h2>Recent media</h2></div><span>{assets.length} item{assets.length === 1 ? '' : 's'}</span></div>
    {loading && <p className="library-state">Loading saved media…</p>}
    {error && <p className="library-state">Could not load saved media. <button type="button" onClick={onRetry}>Retry</button></p>}
    {!loading && !error && assets.length === 0 && <p className="library-state">Uploaded images and videos will appear here.</p>}
    {assets.length > 0 && <div className="library-items">
      {assets.map((asset) => <button type="button" key={asset.media_id} className={`library-item ${asset.media_id === activeId ? 'selected' : ''}`} onClick={() => onSelect(asset.media_id)} aria-pressed={asset.media_id === activeId} title={asset.original_filename}>
        <span className="library-thumbnail">{asset.thumbnail_available ? <img src={mediaThumbnailUrl(asset.media_id)} alt="" loading="lazy" /> : asset.media_type === 'video' ? <Film size={19} /> : <ImageIcon size={19} />}</span>
        <span className="library-item-meta"><strong>{asset.original_filename}</strong><small>{asset.media_type === 'video' ? 'Video' : 'Image'}</small></span>
      </button>)}
    </div>}
  </section>
}
