import { ImageViewer } from '@/components/media/ImageViewer'
import { VideoViewer } from '@/components/media/VideoViewer'
import type { MediaAsset } from '@/types/media'

export function MediaViewer({ asset }: { asset: MediaAsset }) {
  return asset.media_type === 'image' ? <ImageViewer asset={asset} /> : <VideoViewer asset={asset} />
}
