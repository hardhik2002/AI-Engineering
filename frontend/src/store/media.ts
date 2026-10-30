import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface MediaState {
  activeMediaId: string | null
  selectMedia: (id: string | null) => void
}

export const useMediaStore = create<MediaState>()(
  persist(
    (set) => ({ activeMediaId: null, selectMedia: (activeMediaId) => set({ activeMediaId }) }),
    { name: 'visionlab-active-media' },
  ),
)
