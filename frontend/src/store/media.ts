import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface MediaState {
  activeMediaId: string | null
  activeAnalysisId: string | null
  selectMedia: (id: string | null) => void
  selectAnalysis: (id: string | null) => void
}

export const useMediaStore = create<MediaState>()(
  persist(
    (set) => ({ activeMediaId: null, activeAnalysisId: null,
      selectMedia: (activeMediaId) => set({ activeMediaId, activeAnalysisId: null }),
      selectAnalysis: (activeAnalysisId) => set({ activeAnalysisId }),
    }),
    { name: 'visionlab-active-media' },
  ),
)
