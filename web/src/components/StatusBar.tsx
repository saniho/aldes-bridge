import { useEffect, useState } from 'react'
import type { Config, Mode } from '../types'
import styles from './StatusBar.module.css'

interface Props {
  config: Config | null
  sseAlive: boolean
  onMode: (m: Mode) => void
  onDisconnect: () => void
}

const MODES: Mode[] = ['proxy', 'bridge', 'raw']

function fmtDur(sinceEpochS: number | null | undefined, nowMs: number): string | null {
  if (!sinceEpochS) return null
  const s = Math.max(0, Math.floor(nowMs / 1000 - sinceEpochS))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export default function StatusBar({ config, sseAlive, onMode, onDisconnect }: Props) {
  const mode: Mode | null = config?.mode ?? null
  const connected = config?.connected ?? false
  const err = config?.last_error
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const boxDur = fmtDur(config?.box_since, now)
  const cloudDur = fmtDur(config?.cloud_since, now)

  return (
    <div className={styles.bar}>
      <div className={styles.mode}>
        <span className={styles.dot + (mode ? ' ' + (styles[mode] ?? '') : '')} />
        <span>Mode : {mode ?? '—'}</span>
      </div>

      <div className={styles.conn}>
        {connected ? (
          <>
            <span className={styles.ok}>connecté</span>
            {config?.client_id && <code className={styles.cid}>{config.client_id}</code>}
            <span className={styles.uptime} title="durée depuis la connexion de la box">
              box depuis {boxDur ?? '…'}
            </span>
            {config?.cloud_since != null && (
              <span className={styles.uptime + ' ' + styles.cloud} title="durée du lien avec le cloud Azure">
                Azure depuis {cloudDur ?? '…'}
              </span>
            )}
          </>
        ) : (
          <span className={styles.off}>{err ? `erreur : ${err}` : 'aucune box connectée'}</span>
        )}
      </div>

      {config?.topics && config.topics.length > 0 && (
        <div className={styles.topics}>
          {config.topics.map((t) => (
            <span key={t} className={styles.topic}>
              {t}
            </span>
          ))}
        </div>
      )}

      <div className={styles.actions}>
        <span className={styles.sse + (sseAlive ? ' ' + styles.live : '')}>SSE</span>
        <select
          className={styles.modeSel}
          value={mode ?? 'proxy'}
          onChange={(e) => onMode(e.target.value as Mode)}
        >
          {MODES.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        {connected && <button onClick={onDisconnect}>déconnecter</button>}
      </div>
    </div>
  )
}