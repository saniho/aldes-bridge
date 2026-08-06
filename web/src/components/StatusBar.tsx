import type { Config, Mode } from '../types'
import styles from './StatusBar.module.css'

interface Props {
  config: Config | null
  sseAlive: boolean
  onMode: (m: Mode) => void
  onDisconnect: () => void
}

const FLIP = { proxy: 'bridge', bridge: 'proxy' } as const

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
        {mode && (
          <>
            <button onClick={() => onMode(FLIP[mode])}>passer en {FLIP[mode]}</button>
            {connected && <button onClick={onDisconnect}>déconnecter</button>}
          </>
        )}
      </div>
    </div>
  )
}