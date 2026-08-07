import { useEffect, useState } from 'react'
import { getRaw, setRaw } from '../api'
import type { RawConfig } from '../types'
import styles from './RawPanel.module.css'

export default function RawPanel() {
  const [cfg, setCfg] = useState<Partial<RawConfig>>({
    host: '',
    port: 1883,
    tls: true,
    client_id: '',
    cmd_topic: '',
    evt_topic: ''
  })
  const [loaded, setLoaded] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    getRaw()
      .then((r) => {
        setCfg(r)
        setLoaded(true)
      })
      .catch((e) => setStatus(`lecture impossible : ${(e as Error).message}`))
  }, [])

  const set = (k: keyof RawConfig, v: string | boolean | number) =>
    setCfg((c) => ({ ...c, [k]: v }))

  const save = async () => {
    setStatus(null)
    try {
      const r = await setRaw(cfg)
      setCfg(r)
      setStatus('configuration raw enregistrée — reconnexion…')
    } catch (e) {
      setStatus(`erreur : ${(e as Error).message}`)
    }
  }

  return (
    <div className={styles.panel}>
      <h3>Client MQTT natif (raw)</h3>
      {!loaded && <div className={styles.hint}>chargement…</div>}
      <div className={styles.row}>
        <label>Broker host</label>
        <input value={cfg.host ?? ''} onChange={(e) => set('host', e.target.value)} spellCheck={false} />
      </div>
      <div className={styles.row}>
        <label>Port</label>
        <input
          type="number"
          value={cfg.port ?? 1883}
          onChange={(e) => set('port', Number(e.target.value))}
        />
      </div>
      <div className={styles.rowInline}>
        <label>
          <input
            type="checkbox"
            checked={!!cfg.tls}
            onChange={(e) => set('tls', e.target.checked)}
          />{' '}
          TLS
        </label>
      </div>
      <div className={styles.row}>
        <label>Client ID</label>
        <input
          value={cfg.client_id ?? ''}
          onChange={(e) => set('client_id', e.target.value)}
          spellCheck={false}
        />
      </div>
      <div className={styles.row}>
        <label>Cmd topic</label>
        <input
          value={cfg.cmd_topic ?? ''}
          onChange={(e) => set('cmd_topic', e.target.value)}
          spellCheck={false}
        />
      </div>
      <div className={styles.row}>
        <label>Evt topic</label>
        <input
          value={cfg.evt_topic ?? ''}
          onChange={(e) => set('evt_topic', e.target.value)}
          spellCheck={false}
        />
      </div>
      <button className={styles.save} onClick={save}>
        enregistrer & reconnecter
      </button>
      {status && <div className={styles.status}>{status}</div>}
    </div>
  )
}