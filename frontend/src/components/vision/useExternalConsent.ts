import { useState } from 'react'

export function useExternalConsent(mediaId: string | null) {
  const [revision, setRevision] = useState(0)
  const key = mediaId ? `visionlab:openai-consent:${mediaId}` : null
  const consent = !!key && localStorage.getItem(key) === 'yes'
  function setConsent(value: boolean) {
    if (key) {
      if (value) localStorage.setItem(key, 'yes')
      else localStorage.removeItem(key)
      setRevision(revision + 1)
    }
  }
  return { consent, setConsent }
}
