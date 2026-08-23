import { useEffect, useRef, useState } from 'react'
import type { BridgeEvent } from '../types'

export function useSse(enabled: boolean) {
  const [events, setEvents] = useState<BridgeEvent[]>([])
  const [connected, setConnected] = useState(false)
  const ref = useRef<EventSource | null>(null)
  const openedRef = useRef(false)

  useEffect(() => {
    if (!enabled) return

    let closed = false
    let openedSinceError = false
    let watchdog: ReturnType<typeof setTimeout> | null = null

    const open = () => {
      const es = new EventSource('api/events')
      ref.current = es
      es.onopen = () => {
        openedSinceError = true
        openedRef.current = true
        setConnected(true)
      }
      es.onerror = () => {
        setConnected(false)
        // laisse l'EventSource tenter sa reconnexion native ; le watchdog force
        // une référence neuve si elle ne revient pas à flot rapidement.
      }
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as BridgeEvent
          setEvents((prev) => {
            if (data.kind === 'snapshot') return [data]
            return [...prev, data].slice(-500)
          })
        } catch {
          /* trame malformée ignorée */
        }
      }
      // Watchdog : si la connexion n'aboutit pas peu après (que ce soit le 1er
      // essai ou une reconnexion), on détruit et on repart d'une référence neuve.
      watchdog = setTimeout(() => {
        if (closed || openedSinceError) return
        es.close()
        if (!closed) open()
      }, 4000)
    }

    open()

    return () => {
      closed = true
      if (watchdog) clearTimeout(watchdog)
      if (ref.current) ref.current.close()
      ref.current = null
      openedRef.current = false
      setConnected(false)
    }
  }, [enabled])

  return { events, connected }
}