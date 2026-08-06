import { useEffect, useRef, useState } from 'react'
import type { BridgeEvent } from '../types'

export function useSse(enabled: boolean) {
  const [events, setEvents] = useState<BridgeEvent[]>([])
  const [connected, setConnected] = useState(false)
  const ref = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!enabled) return
    const es = new EventSource('/api/events')
    ref.current = es
    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as BridgeEvent
        setEvents((prev) => {
          if (data.kind === 'snapshot') return [data]
          return [...prev, data].slice(-500)
        })
      } catch {
        /* ignore malformed frames */
      }
    }
    return () => {
      es.close()
      setConnected(false)
    }
  }, [enabled])

  return { events, connected }
}