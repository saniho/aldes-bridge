import { useEffect, useMemo, useState } from 'react'
import { sendCommand } from '../api'
import type { Mode } from '../types'
import styles from './SendPanel.module.css'

interface Props {
  mode: Mode | null
  connected: boolean
  clientId: string | null
  defaultTopic?: string | null
}

interface ThermoRow {
  id: string
  name: string
  temp: string
}

const MODES: { code: string; label: string }[] = [
  { code: 'V', label: 'V · Quotidien' },
  { code: 'X', label: 'X · Boost' },
  { code: 'Y', label: 'Y · Invités' },
  { code: 'Z', label: 'Z · Programme' },
  { code: 'H', label: 'H · Hors-gel' },
  { code: 'E', label: 'E · Auto' },
  { code: 'A', label: 'A · Arrêt' },
  { code: 'B', label: 'B · Chaud (Heat)' },
  { code: 'F', label: 'F · Froid (Cool)' }
]

const FNS: { id: string; label: string }[] = [
  { id: 'mode', label: 'changeMode — mode' },
  { id: 'vacances', label: 'changeMode — vacances (W)' },
  { id: 'cmo', label: 'changeCMO — override 0/1' },
  { id: 'thermostats', label: 'updateThermostats' },
  { id: 'deltat', label: 'changeTemperatureReference' },
  { id: 'custom', label: 'JSON libre (personnalisé)' }
]

const THERMOS: { id: string; name: string; label: string }[] = [
  { id: '76542', name: 'Piece Principale', label: 'Piece Principale → 76542' },
  { id: '76543', name: 'Ch Parents', label: 'Ch Parents → 76543' },
  { id: '76544', name: 'Ch Romane', label: 'Ch Romane → 76544' },
  { id: '76545', name: 'Ch Marine', label: 'Ch Marine → 76545' },
  { id: '76546', name: 'Bureau', label: 'Bureau → 76546' }
]

function presetsFrom(id: string) {
  return THERMOS.some((th) => th.id === id)
}

function topicFor(clientId: string): string {
  return `devices/${clientId}/messages/devicebound`
}

function utcStamp(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}` +
    `${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`
  )
}

function dateInputValue(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export default function CommandBuilder({ connected, clientId, defaultTopic }: Props) {
  const [fn, setFn] = useState('mode')
  const [modeSel, setModeSel] = useState('V')
  const [modeFree, setModeFree] = useState(false)
  const [customCode, setCustomCode] = useState('')
  const [vacStart, setVacStart] = useState('')
  const [vacEnd, setVacEnd] = useState('')
  const [cmo, setCmo] = useState('1')
  const [thermos, setThermos] = useState<ThermoRow[]>([
    { id: THERMOS[0].id, name: THERMOS[0].name, temp: '21' }
  ])
  const [deltat, setDeltat] = useState('21')
  const [json, setJson] = useState('')
  const [topic, setTopic] = useState('')
  const [qos, setQos] = useState(1)
  const [status, setStatus] = useState<string | null>(null)

  const targetTopic = useMemo(() => {
    if (defaultTopic) return defaultTopic
    return clientId ? topicFor(clientId) : null
  }, [defaultTopic, clientId])

  useEffect(() => {
    if (targetTopic && !topic) {
      setTopic(targetTopic)
      setStatus('topic auto : ' + targetTopic)
    }
  }, [targetTopic]) // eslint-disable-line react-hooks/exhaustive-deps

  const payload = useMemo((): string | null => {
    if (fn === 'mode') {
      const code = (modeFree ? customCode.trim() : modeSel).toUpperCase()
      if (!code) return null
      return `{"method":"changeMode","params":["${code}"]}`
    }
    if (fn === 'vacances') {
      const s = vacStart ? utcStamp(new Date(vacStart)) : ''
      const e = vacEnd ? utcStamp(new Date(vacEnd)) : ''
      if (!s || !e) return null
      return `{"method":"changeMode","params":["W${s}${e}"]}`
    }
    if (fn === 'cmo') {
      const v = cmo === '1' ? 1 : 0
      return `{"method":"changeCMO","params":[${v}]}`
    }
    if (fn === 'thermostats') {
      const rows = thermos
        .map((r) => {
          const id = Number(r.id.trim())
          const temp = Number(r.temp)
          if (!r.id.trim() || Number.isNaN(id) || Number.isNaN(temp)) return null
          const obj: Record<string, number | string> = { ThermostatId: id, TemperatureSet: temp }
          if (r.name.trim()) obj.Name = r.name.trim()
          return obj
        })
        .filter((x): x is Record<string, number | string> => x !== null)
      if (!rows.length) return null
      return `{"method":"updateThermostats","params":${JSON.stringify(rows)}}`
    }
    if (fn === 'deltat') {
      const v = Number(deltat)
      if (Number.isNaN(v)) return null
      return `{"method":"changeTemperatureReference","params":[${v}]}`
    }
    if (fn === 'custom') {
      if (!json.trim()) return null
      try {
        JSON.parse(json)
      } catch {
        return null
      }
      return json.trim()
    }
    return null
  }, [fn, modeSel, modeFree, customCode, vacStart, vacEnd, cmo, thermos, deltat, json])

  const setThermo = (i: number, key: keyof ThermoRow, v: string) =>
    setThermos((rows) => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)))

  const submit = async () => {
    setStatus(null)
    if (!topic.trim()) return setStatus('topic requis')
    if (!payload) return setStatus('params incomplets')
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
      <h3>Commande à la box</h3>

      <div className={styles.row}>
        <label>Fonction</label>
        <select value={fn} onChange={(e) => setFn(e.target.value)}>
          {FNS.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label}
            </option>
          ))}
        </select>
      </div>

      {fn === 'mode' && (
        <>
          <div className={styles.row}>
            <label>Mode</label>
            <select
              value={modeFree ? '__free' : modeSel}
              onChange={(e) => {
                if (e.target.value === '__free') {
                  setModeFree(true)
                  setCustomCode('')
                } else {
                  setModeFree(false)
                  setModeSel(e.target.value)
                }
              }}
            >
              {MODES.map((m) => (
                <option key={m.code} value={m.code}>
                  {m.label}
                </option>
              ))}
              <option value="__free">Personnalisé…</option>
            </select>
          </div>
          {modeFree && (
            <div className={styles.row}>
              <label>Code</label>
              <input
                value={customCode}
                onChange={(e) => setCustomCode(e.target.value)}
                placeholder="ex. V, X, W…"
                spellCheck={false}
              />
            </div>
          )}
        </>
      )}

      {fn === 'vacances' && (
        <>
          <div className={styles.row}>
            <label>Début</label>
            <input type="datetime-local" value={vacStart} onChange={(e) => setVacStart(e.target.value)} />
          </div>
          <div className={styles.row}>
            <label>Fin</label>
            <input type="datetime-local" value={vacEnd} onChange={(e) => setVacEnd(e.target.value)} />
          </div>
          <div className={styles.hint}>
            <button
              type="button"
              onClick={() => {
                const now = new Date()
                const later = new Date(now.getTime() + 7 * 86400000)
                setVacStart(dateInputValue(now))
                setVacEnd(dateInputValue(later))
              }}
            >
              +7 jours
            </button>
            <span>envoie <code>W…Z…Z</code> (UTC)</span>
          </div>
        </>
      )}

      {fn === 'cmo' && (
        <div className={styles.row}>
          <label>Valeur</label>
          <select value={cmo} onChange={(e) => setCmo(e.target.value)}>
            <option value="1">1 · ON (override)</option>
            <option value="0">0 · OFF</option>
          </select>
        </div>
      )}

      {fn === 'thermostats' && (
        <>
          {thermos.map((t, i) => {
            const isPreset = presetsFrom(t.id)
            return (
              <div className={styles.row} key={i}>
                <label>T{i + 1}</label>
                <select
                  value={isPreset ? t.id : '__free'}
                  onChange={(e) => {
                    if (e.target.value === '__free') {
                      setThermo(i, 'id', '')
                      setThermo(i, 'name', '')
                    } else {
                      const th = THERMOS.find((x) => x.id === e.target.value)!
                      setThermo(i, 'id', th.id)
                      setThermo(i, 'name', th.name)
                    }
                  }}
                >
                  {THERMOS.map((th) => (
                    <option key={th.id} value={th.id}>
                      {th.label}
                    </option>
                  ))}
                  <option value="__free">Personnalisé…</option>
                </select>
                {!isPreset && (
                  <input
                    placeholder="ThermostatId"
                    value={t.id}
                    onChange={(e) => setThermo(i, 'id', e.target.value)}
                  />
                )}
                <input
                  placeholder="Object °C"
                  value={t.temp}
                  onChange={(e) => setThermo(i, 'temp', e.target.value)}
                />
                <button type="button" onClick={() => setThermos((rows) => rows.filter((_, j) => j !== i))}>
                  ×
                </button>
              </div>
            )
          })}
          <div className={styles.hint}>
            <button
              type="button"
              onClick={() => setThermos((rows) => [...rows, { id: THERMOS[0].id, name: THERMOS[0].name, temp: '21' }])}
            >
              + thermostat
            </button>
          </div>
        </>
      )}

      {fn === 'deltat' && (
        <div className={styles.row}>
          <label>ΔT °C</label>
          <input
            type="number"
            step="0.5"
            value={deltat}
            onChange={(e) => setDeltat(e.target.value)}
          />
        </div>
      )}

      {fn === 'custom' && (
        <div className={styles.row}>
          <label>JSON</label>
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            rows={4}
            spellCheck={false}
            placeholder='{"method":"...","params":[...]}'
          />
        </div>
      )}

      <div className={styles.row}>
        <label>Topic</label>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} spellCheck={false} />
      </div>

      <div className={styles.row}>
        <label>QoS</label>
        <select value={qos} onChange={(e) => setQos(Number(e.target.value))}>
          <option value={0}>0</option>
          <option value={1}>1</option>
          <option value={2}>2</option>
        </select>
        <button onClick={submit} disabled={!connected || !payload}>
          envoyer
        </button>
      </div>

      {payload && (
        <div className={styles.hint}>
          <code>{payload}</code>
        </div>
      )}

      {status && <div className={styles.status}>{status}</div>}
      {!connected && (
        <div className={styles.warn}>box non connectée — envoi impossible pour l'instant</div>
      )}
    </div>
  )
}