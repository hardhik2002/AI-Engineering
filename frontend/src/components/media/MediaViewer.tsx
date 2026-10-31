import { ImageViewer } from '@/components/media/ImageViewer'
import { VideoViewer } from '@/components/media/VideoViewer'
import type { MediaAsset } from '@/types/media'
import type { DetectionOverlay, RegionOverlay } from '@/types/media'
import type { TimestampedAnalysisResult } from '@/types/media'
import type { VideoCaption, VideoFrameResult } from '@/types/video'

export function MediaViewer({ asset, detections, regions, selectedId, selectedRegionId, onSelect, onSelectRegion, showLabels = true, showConfidence = true, videoFrames, videoCaptions, videoMarkers, videoFps, selectedTrackId, videoConfidence, excludedVideoClasses, showVideoBoxes, showVideoCaptions, seekRequest, onVideoTimeChange }: {
  asset: MediaAsset; detections?: DetectionOverlay[]; regions?: RegionOverlay[]; selectedId?: string | null; selectedRegionId?: string | null;
  onSelect?: (id: string | null) => void; onSelectRegion?: (id: string) => void; showLabels?: boolean; showConfidence?: boolean
  videoFrames?: VideoFrameResult[]; videoCaptions?: VideoCaption[]; videoMarkers?: TimestampedAnalysisResult[];
  videoFps?: number; selectedTrackId?: number | null; videoConfidence?: number; excludedVideoClasses?: string[];
  showVideoBoxes?: boolean; showVideoCaptions?: boolean; seekRequest?: { ms: number; nonce: number } | null;
  onVideoTimeChange?: (timestampMs: number) => void
}) {
  return asset.media_type === 'image' ? <ImageViewer asset={asset} detections={detections} regions={regions} selectedId={selectedId} selectedRegionId={selectedRegionId} onSelect={onSelect} onSelectRegion={onSelectRegion} showLabels={showLabels} showConfidence={showConfidence} /> : <VideoViewer asset={asset} frames={videoFrames} captions={videoCaptions} markers={videoMarkers} analysisFps={videoFps} selectedTrackId={selectedTrackId} displayConfidence={videoConfidence} excludedClasses={excludedVideoClasses} showBoxes={showVideoBoxes} showCaptions={showVideoCaptions} showLabels={showLabels} showConfidence={showConfidence} seekRequest={seekRequest} onTimeChange={onVideoTimeChange} />
}
