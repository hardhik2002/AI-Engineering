import { ImageViewer } from '@/components/media/ImageViewer'
import { VideoViewer } from '@/components/media/VideoViewer'
import type { MediaAsset } from '@/types/media'
import type { DetectionOverlay } from '@/types/media'

export function MediaViewer({ asset, detections, selectedId, onSelect, showLabels = true, showConfidence = true }: {
  asset: MediaAsset; detections?: DetectionOverlay[]; selectedId?: string | null;
  onSelect?: (id: string | null) => void; showLabels?: boolean; showConfidence?: boolean
}) {
  return asset.media_type === 'image' ? <ImageViewer asset={asset} detections={detections} selectedId={selectedId} onSelect={onSelect} showLabels={showLabels} showConfidence={showConfidence} /> : <VideoViewer asset={asset} />
}
