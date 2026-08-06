import { useEffect, useMemo, useState } from 'react'
import { sendCommand } from '../api'
import type { Mode } from '../types'
import styles from './SendPanel.module.css'

interface Props {
  mode: Mode | null
  connected: boolean
  clientId: string | null
}

const PRESETS: { label: string; payload: string }[] = [
  {
    label: 'Change ΔT [21.0]',
    payload: '{"method":"changeTemperatureReference","params":[21.0]}'
  },
  {
    label: 'Change ΔT thermostat 1 [21]',
    payload:
      '{"method":"changeTemperatureReference","params":[{"ThermostatId":1,"TemperatureSet":21}]}'
  },
  {
    label: 'Update thermostats',
    payload: '{"method":"updateThermostats","params":[{"ThermostatId":1,"TemperatureSet":21}]}'
  }
]

function topicFor(clientId: string): string {
  return `devices/${clientId}/messages/devicebound`
}

export default function SendPanel({ connected, clientId }: Props) {
  const [topic, setTopic] = useState('')
  const [payload, setPayload] = useState('')
  const [preset, setPreset] = useState('')
  const [qos, setQos] = useState(0)
  const [status, setStatus] = useState<string | null>(null)

  const targetTopic = useMemo(
    () => (clientId ? topicFor(clientId) : null),
    [clientId]
  )

  useEffect(() => {
    if (targetTopic && !topic) {
      setTopic(targetTopic)
      setStatus('topic auto : ' + targetTopic)
    }
  }, [targetTopic]) // eslint-disable-line react-hooks/exhaustive-deps

  const onPreset = (value: string) => {
    setPreset(value)
    if (value) {
      const found = PRESETS.find((p) => p.payload === value)
      if (found) setPayload(found.payload)
    }
  }

  const submit = async () => {
    setStatus(null)
    if (!topic.trim()) return setStatus('topic requis')
    if (!payload.trim()) return setStatus('payload requis')
    try {
      const r = await sendCommand(topic.trim(), payload, qos)
      setStatus(
        `envoyé : ${r.topic ?? topic} / qos ${r.qos ?? qos}${
          r.bytes !== undefined ? ` (${r.bytes} octets)` : ''
        }`
      )
    } catch (e) {
      setStatus(`erreur : ${(e as Error).message}`)
    }
  }

  return (
    <div className={styles.panel}>
      <h3>Envoyer une commande MQTT</h3>
      <div className={styles.row}>
        <label>Topic</label>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="devices/<id>/messages/devicebound"
          spellCheck={false}
        />
      </div>
      {targetTopic && (
        <div className={styles.hint}>
          auto : <code>{targetTopic}</code>
          <button type="button" onClick={() => setTopic(targetTopic)}>
            réappliquer
          </button>
        </div>
      )}
      <div className={styles.row}>
        <label>Commande</label>
        <select
          value={preset}
          onChange={(e) => onPreset(e.target.value)}
        >
          <option value="">(personnalisé)</option>
          {PRESETS.map((p) => (
            <option key={p.payload} value={p.payload}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
      <div className={styles.row}>
        <label>Payload (JSON)</label>
        <textarea
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          rows={4}
          spellCheck={false}
          placeholder='{"method":"...","params":[...]}'
        />
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
      {!connected && (
        <div className={styles.warn}>box non connectée — envoi impossible pour l'instant</div>
      )}
    </div>
  )
}