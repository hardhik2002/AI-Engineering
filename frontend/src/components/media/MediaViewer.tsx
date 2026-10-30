import { ImageViewer } from '@/components/media/ImageViewer'
import { VideoViewer } from '@/components/media/VideoViewer'
import type { MediaAsset } from '@/types/media'
import type { DetectionOverlay, RegionOverlay } from '@/types/media'

export function MediaViewer({ asset, detections, regions, selectedId, selectedRegionId, onSelect, onSelectRegion, showLabels = true, showConfidence = true }: {
  asset: MediaAsset; detections?: DetectionOverlay[]; regions?: RegionOverlay[]; selectedId?: string | null; selectedRegionId?: string | null;
  onSelect?: (id: string | null) => void; onSelectRegion?: (id: string) => void; showLabels?: boolean; showConfidence?: boolean
}) {
  return asset.media_type === 'image' ? <ImageViewer asset={asset} detections={detections} regions={regions} selectedId={selectedId} selectedRegionId={selectedRegionId} onSelect={onSelect} onSelectRegion={onSelectRegion} showLabels={showLabels} showConfidence={showConfidence} /> : <VideoViewer asset={asset} />
}
