import { useEffect, useMemo, useState } from 'react'
import type { MsgEvent } from '../types'
import styles from './StatsBar.module.css'

interface Props {
  messages: MsgEvent[]
  connected: boolean
  staleAfter?: number
}

function isoToMs(ts: string): number {
  const ms = Date.parse(ts)
  return Number.isNaN(ms) ? 0 : ms
}

export default function StatsBar({ messages, connected, staleAfter = 15 }: Props) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const stats = useMemo(() => {
    let up = 0
    let down = 0
    let bytes = 0
    let last = 0
    for (const m of messages) {
      const n = m.payload ? m.payload.length : 0
      bytes += n
      if (m.direction === 'in') up++
      else down++
      const t = isoToMs(m.ts)
      if (t > last) last = t
    }
    return { up, down, bytes, last }
  }, [messages])

  const activity = stats.last ? Math.max(0, Math.floor((now - stats.last) / 1000)) : null
  const stale = connected && activity !== null && activity > staleAfter

  const fmt = (s: number) => (s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m${s % 60}s` : `${Math.floor(s / 3600)}h`)

  return (
    <div className={styles.bar}>
      <span className={styles.stat} title="messages box → cloud">
        ▲ {stats.up}
      </span>
      <span className={styles.stat} title="messages cloud → box">
        ▼ {stats.down}
      </span>
      <span className={styles.stat} title="octets de payload capturés">
        {stats.bytes.toLocaleString()} B
      </span>
      <span className={styles.stat} title="dernière activité">
        {activity === null ? '—' : `il y a ${fmt(activity)}`}
      </span>
      <span
        className={styles.flow + ' ' + (stale ? styles.stale : connected ? styles.live : styles.off)}
        title={stale ? `flux suspendu (pas de trafic depuis ${fmt(activity!)}s)` : 'flux actif'}
      >
        {stale ? '● flux suspendu' : connected ? '● actif' : '○ hors ligne'}
      </span>
    </div>
  )
}