import type { Config, Mode } from '../types'
import styles from './StatusBar.module.css'

interface Props {
  config: Config | null
  sseAlive: boolean
  onMode: (m: Mode) => void
  onDisconnect: () => void
}

const MODES: Mode[] = ['proxy', 'bridge', 'raw']

export default function StatusBar({ config, sseAlive, onMode, onDisconnect }: Props) {
  const mode: Mode | null = config?.mode ?? null
  const connected = config?.connected ?? false
  const err = config?.last_error

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