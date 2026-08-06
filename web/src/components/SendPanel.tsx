import { useState } from 'react'
import { sendCommand } from '../api'
import type { Mode } from '../types'
import styles from './SendPanel.module.css'

interface Props {
  mode: Mode | null
  connected: boolean
}

const TOPIC_TEMPLATE = 'devices/<boxid>/messages/devicebound'

export default function SendPanel({ connected }: Props) {
  const [topic, setTopic] = useState('')
  const [payload, setPayload] = useState('{}')
  const [qos, setQos] = useState(0)
  const [status, setStatus] = useState<string | null>(null)

  const submit = async () => {
    setStatus(null)
    if (!topic.trim()) return setStatus('topic requis')
    try {
      const r = await sendCommand(topic.trim(), payload, qos)
      setStatus(
        `envoyé : ${r.topic ?? topic} / qos ${r.qos ?? qos}${r.bytes !== undefined ? ` (${r.bytes} octets)` : ''}`
      )
    } catch (e) {
      setStatus(`erreur : ${(e as Error).message}`)
    }
  }

  const useTemplate = () => {
    setTopic(TOPIC_TEMPLATE)
    setStatus('template topic — remplace <boxid> si besoin')
  }

  return (
    <div className={styles.panel}>
      <h3>Envoyer une commande MQTT</h3>
      <div className={styles.row}>
        <label>Topic</label>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder={TOPIC_TEMPLATE}
          spellCheck={false}
        />
        <button onClick={useTemplate} type="button">
          template
        </button>
      </div>
      <div className={styles.row}>
        <label>Payload (JSON)</label>
        <textarea value={payload} onChange={(e) => setPayload(e.target.value)} rows={4} spellCheck={false} />
      </div>
      <div className={styles.row}>
        <label>QoS</label>
        <select value={qos} onChange={(e) => setQos(Number(e.target.value))}>
          <option value={0}>0</option>
          <option value={1}>1</option>
          <option value={2}>2</option>
        </select>
        <button onClick={submit} disabled={!connected}>
          envoyer
        </button>
      </div>
      {status && <div className={styles.status}>{status}</div>}
      {!connected && <div className={styles.warn}>box non connectée — envoi impossible pour l'instant</div>}
    </div>
  )
}