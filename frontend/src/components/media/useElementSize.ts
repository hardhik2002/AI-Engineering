import { useEffect, useState, type RefObject } from 'react'

export function useElementSize(ref: RefObject<HTMLElement | null>) {
  const [size, setSize] = useState({ width: 720, height: 440 })
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const measure = () => {
      const bounds = element.getBoundingClientRect()
      if (bounds.width > 0 && bounds.height > 0) setSize({ width: bounds.width, height: bounds.height })
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return size
}
