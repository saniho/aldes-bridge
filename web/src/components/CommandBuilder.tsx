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
  str: boolean
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
  { id: 'consigne', label: 'changeConsigneC<n> — consigne par zone (réel cloud)' },
  { id: 'mode', label: 'changeMode — mode' },
  { id: 'vacances', label: 'changeMode — vacances (W)' },
  { id: 'cmo', label: 'changeCMO — override 0/1' },
  { id: 'thermostats', label: 'updateThermostats' },
  { id: 't2', label: 'changeTemperatureReference — par thermostat (T2)' },
  { id: 'deltat', label: 'changeTemperatureReference' },
  { id: 'custom', label: 'JSON libre (personnalisé)' }
]

const ZONES: { id: string; label: string }[] = [
  { id: 'C0', label: 'C0 · Zone 1 (principale)' },
  { id: 'C1', label: 'C1 · Zone 2' },
  { id: 'C2', label: 'C2 · Zone 3' },
  { id: 'C3', label: 'C3 · Zone 4' },
  { id: 'C4', label: 'C4 · Zone 5' },
  { id: 'C5', label: 'C5 · Zone 6' },
  { id: 'C6', label: 'C6 · Zone 7' },
  { id: 'C7', label: 'C7 · Zone 8' },
  { id: 'C8', label: 'C8 · Zone 9' },
  { id: 'C9', label: 'C9 · Zone 10' }
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

function randHex(n: number): string {
  let s = ''
  for (let i = 0; i < n; i++) s += Math.floor(Math.random() * 16).toString(16)
  return s
}

function randomUUID(): string {
  return (
    `${randHex(8)}-${randHex(4)}-4${randHex(3)}-` +
    `${(8 + Math.floor(Math.random() * 4)).toString(16)}${randHex(3)}-` +
    `${randHex(12)}`
  )
}

function withPropBag(base: string, clientId: string | null): string {
  const m = base.match(/^devices\/([^/]+)\/messages\/devicebound$/)
  const id = m ? m[1] : clientId ?? ''
  const mid = randomUUID()
  const to = encodeURIComponent(`/devices/${id}/messages/deviceBound`)
  return `${base}/%24.mid=${mid}&%24.to=${to}&iothub-ack=full`
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
  const [fn, setFn] = useState('consigne')
  const [consZone, setConsZone] = useState('C0')
  const [consZoneFree, setConsZoneFree] = useState(false)
  const [consTemp, setConsTemp] = useState('21')
  const [modeSel, setModeSel] = useState('V')
  const [modeFree, setModeFree] = useState(false)
  const [customCode, setCustomCode] = useState('')
  const [vacStart, setVacStart] = useState('')
  const [vacEnd, setVacEnd] = useState('')
  const [cmo, setCmo] = useState('1')
  const [thermos, setThermos] = useState<ThermoRow[]>([
    { id: THERMOS[0].id, name: THERMOS[0].name, temp: '21', str: false }
  ])
  const [deltat, setDeltat] = useState('21')
  const [json, setJson] = useState('')
  const [rpc, setRpc] = useState(true)
  const [propbag, setPropbag] = useState(false)
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
    const wrap = (method: string, params: string): string => {
      const body = `{"method":"${method}","params":${params}}`
      if (!rpc) return body
      return `{"id":1,"jsonrpc":"2.0",${body.slice(1)}`
    }
    const dbl = (v: number): string => (Number.isInteger(v) ? `${v}.0` : String(v))

    const rowsOf = (): Record<string, number | string>[] | null =>
      thermos
        .map((r) => {
          const raw = r.id.trim()
          const temp = Number(r.temp)
          if (!raw || Number.isNaN(temp)) return null
          const id = r.str ? raw : Number(raw)
          if (!r.str && Number.isNaN(id)) return null
          const obj: Record<string, number | string> = { ThermostatId: id, TemperatureSet: temp }
          if (r.name.trim()) obj.Name = r.name.trim()
          return obj
        })
        .filter((x): x is Record<string, number | string> => x !== null)

    if (fn === 'consigne') {
      const zone = (consZoneFree ? consZone.trim() : consZone).toUpperCase()
      const temp = Number(consTemp)
      if (!/^C\d{1,2}$/.test(zone) || Number.isNaN(temp)) return null
      return wrap(`changeConsigne${zone}`, JSON.stringify([consTemp.trim()]))
    }
    if (fn === 'mode') {
      const code = (modeFree ? customCode.trim() : modeSel).toUpperCase()
      if (!code) return null
      return wrap('changeMode', JSON.stringify([code]))
    }
    if (fn === 'vacances') {
      const s = vacStart ? utcStamp(new Date(vacStart)) : ''
      const e = vacEnd ? utcStamp(new Date(vacEnd)) : ''
      if (!s || !e) return null
      return wrap('changeMode', JSON.stringify([`W${s}${e}`]))
    }
    if (fn === 'cmo') {
      const v = cmo === '1' ? 1 : 0
      return wrap('changeCMO', `[${v}]`)
    }
    if (fn === 'thermostats') {
      const rows = rowsOf()
      if (!rows?.length) return null
      return wrap('updateThermostats', JSON.stringify(rows))
    }
    if (fn === 't2') {
      const rows = rowsOf()
      if (!rows?.length) return null
      return wrap('changeTemperatureReference', JSON.stringify(rows))
    }
    if (fn === 'deltat') {
      const v = Number(deltat)
      if (Number.isNaN(v)) return null
      return wrap('changeTemperatureReference', `[${dbl(v)}]`)
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
  }, [fn, consZone, consZoneFree, consTemp, modeSel, modeFree, customCode, vacStart, vacEnd, cmo, thermos, deltat, json, rpc])

  const setThermo = (i: number, key: keyof ThermoRow, v: string | boolean) =>
    setThermos((rows) => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)))

  const submit = async () => {
    setStatus(null)
    if (!topic.trim()) return setStatus('topic requis')
    if (!payload) return setStatus('params incomplets')
    const effTopic = propbag ? withPropBag(topic.trim(), clientId) : topic.trim()
    try {
      const r = await sendCommand(effTopic, payload, qos)
      if (!r.ok) {
        setStatus(`refusé côté serveur${r.error ? ' : ' + r.error : ''}`)
        return
      }
      setStatus(
        `envoyé : ${r.topic ?? effTopic} / qos ${r.qos ?? qos}${
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

      {fn === 'consigne' && (
        <>
          <div className={styles.row}>
            <label>Zone</label>
            <select
              value={consZoneFree ? '__free' : consZone}
              onChange={(e) => {
                if (e.target.value === '__free') {
                  setConsZoneFree(true)
                } else {
                  setConsZoneFree(false)
                  setConsZone(e.target.value)
                }
              }}
            >
              {ZONES.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.label}
                </option>
              ))}
              <option value="__free">Personnalisé…</option>
            </select>
            {consZoneFree && (
              <input
                value={consZone}
                onChange={(e) => setConsZone(e.target.value)}
                placeholder="ex. C3"
                spellCheck={false}
              />
            )}
          </div>
          <div className={styles.row}>
            <label>Consigne °C</label>
            <input
              type="number"
              step="0.5"
              value={consTemp}
              onChange={(e) => setConsTemp(e.target.value)}
            />
          </div>
          <div className={styles.hint}>
            <span>
              <code>changeConsigneC0..C9</code> · params en chaîne <code>{'["21"]'}</code> — format
              réellement utilisé par le cloud Aldes (C0 = zone principale)
            </span>
          </div>
        </>
      )}

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

      {(fn === 'thermostats' || fn === 't2') && (
        <>
          {thermos.map((t, i) => {
            const isPreset = presetsFrom(t.id)
            return (
              <div className={`${styles.row} ${styles.thermoRow}`} key={i}>
                <label>T{i + 1}</label>
                <select
                  value={isPreset ? t.id : '__free'}
                  onChange={(e) => {
                    if (e.target.value === '__free') {
                      setThermo(i, 'id', '')
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
                <input
                  placeholder="ThermostatId"
                  value={t.id}
                  onChange={(e) => setThermo(i, 'id', e.target.value)}
                />
                <input
                  placeholder="Nom (opt.)"
                  value={t.name}
                  onChange={(e) => setThermo(i, 'name', e.target.value)}
                />
                <input
                  placeholder="Object °C"
                  value={t.temp}
                  onChange={(e) => setThermo(i, 'temp', e.target.value)}
                />
                <label className={styles.strToggle}>
                  <input
                    type="checkbox"
                    checked={t.str}
                    onChange={(e) => setThermo(i, 'str', e.target.checked)}
                  />
                  string
                </label>
                <button type="button" onClick={() => setThermos((rows) => rows.filter((_, j) => j !== i))}>
                  ×
                </button>
              </div>
            )
          })}
          <div className={styles.hint}>
            <button
              type="button"
              onClick={() => setThermos((rows) => [...rows, { id: THERMOS[0].id, name: THERMOS[0].name, temp: '21', str: false }])}
            >
              + thermostat
            </button>
          </div>
          {fn === 't2' && (
            <div className={styles.hint}>
              <span>
                changeTemperatureReference · params = objet thermostat{' '}
                <code>{`[{"ThermostatId":1,"TemperatureSet":21}]`}</code>
              </span>
            </div>
          )}
        </>
      )}

      {fn === 'deltat' && (
        <>
          <div className={styles.row}>
            <label>ΔT °C</label>
            <input
              type="number"
              step="0.5"
              value={deltat}
              onChange={(e) => setDeltat(e.target.value)}
            />
          </div>
          <div className={styles.hint}>
            <span>changeTemperatureReference · params en <code>double</code> (ex. <code>21.0</code>)</span>
          </div>
        </>
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
        <label className={styles.strToggle}>
          <input
            type="checkbox"
            checked={rpc}
            onChange={(e) => setRpc(e.target.checked)}
          />
          JSON-RPC 2.0
        </label>
        <label className={styles.strToggle}>
          <input
            type="checkbox"
            checked={propbag}
            onChange={(e) => setPropbag(e.target.checked)}
            title="Ajoute %24.mid, %24.to, iothub-ack au topic devicebound (format C2D Azure réel)"
          />
          property bag C2D
        </label>
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