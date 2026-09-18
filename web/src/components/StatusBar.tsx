import { useEffect, useState } from 'react'
import type { Config, HealthData, Mode } from '../types'
import styles from './StatusBar.module.css'

interface Props {
  config: Config | null
  sseAlive: boolean
  onMode: (m: Mode) => void
  onDisconnect: () => void
}

const MODES: Mode[] = ['proxy', 'bridge', 'listen', 'raw']

function fmtDur(sinceEpochS: number | null | undefined, nowMs: number): string | null {
  if (!sinceEpochS) return null
  const s = Math.max(0, Math.floor(nowMs / 1000 - sinceEpochS))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m${s % 60}s`
  return `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`
}

export default function StatusBar({ config, sseAlive, onMode, onDisconnect }: Props) {
  const mode: Mode | null = config?.mode ?? null
  const connected = config?.connected ?? false
  const err = config?.last_error
  const health: HealthData | null = config?.health ?? null
  const extTemp = health?.text_ext
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const boxDur = fmtDur(config?.box_since, now)
  const cloudDur = fmtDur(config?.cloud_since, now)

  return (
    <div className={styles.bar}>
      {/* Left: mode + status */}
      <div className={styles.left}>
        <span className={styles.dot + (mode ? ' ' + (styles[mode] ?? '') : '')} />
        <span className={styles.modeLabel}>{mode ?? '—'}</span>
        <span className={styles.sep}>·</span>
        {connected ? (
          <span className={styles.ok}>
            connecté
            {boxDur && <span className={styles.dur}>box {boxDur}</span>}
            {cloudDur && <span className={styles.dur + ' ' + styles.cloud}>Azure {cloudDur}</span>}
          </span>
        ) : (
          <span className={styles.off}>{err ?? 'déconnecté'}</span>
        )}
      </div>

      {/* Center: ext temp */}
      {extTemp != null && (
        <div className={styles.center}>
          <span className={styles.extTemp}>{extTemp.toFixed(1)}°C</span>
          <span className={styles.extLabel}>ext</span>
        </div>
      )}

      {/* Right: actions */}
      <div className={styles.right}>
        {config?.topics && config.topics.length > 0 && (
          <span className={styles.topicsBadge} title={config.topics.join('\n')}>
            {config.topics.length} topic{config.topics.length > 1 ? 's' : ''}
          </span>
        )}
        <span className={styles.sse + (sseAlive ? ' ' + styles.live : '')}>SSE</span>
        <select
          className={styles.modeSel}
          value={mode ?? 'proxy'}
          onChange={(e) => onMode(e.target.value as Mode)}
        >
          {MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        {connected && <button onClick={onDisconnect}>×</button>}
      </div>
    </div>
  )
}
