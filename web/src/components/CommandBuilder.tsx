import { useEffect, useMemo, useState } from 'react'
import { sendCommand } from '../api'
import type { Mode } from '../types'
import { FNS, topicFor, withPropBag } from './commandBuilderData'
import {
  ConsigneSection, ModeSection, BallonSection, AirSection,
  VacancesSection, CmoSection, CustomSection
} from './CommandFormSections'
import styles from './SendPanel.module.css'

interface Props {
  mode: Mode | null
  connected: boolean
  clientId: string | null
  defaultTopic?: string | null
  theme: 'nuit' | 'jour'
}

export default function CommandBuilder({ connected, clientId, defaultTopic, theme }: Props) {
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
  const [ballon, setBallon] = useState('on')
  const [airMode, setAirMode] = useState('F')
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
    if (fn === 'ballon') {
      return wrap('changeMode', JSON.stringify([ballon === 'off' ? 'L' : 'M']))
    }
    if (fn === 'air') {
      return wrap('changeMode', JSON.stringify([airMode]))
    }
    if (fn === 'vacances') {
      const s = vacStart ? new Date(vacStart).toISOString().replace(/[-:T]/g, '').slice(0, 15) + 'Z' : ''
      const e = vacEnd ? new Date(vacEnd).toISOString().replace(/[-:T]/g, '').slice(0, 15) + 'Z' : ''
      if (!s || !e) return null
      return wrap('changeMode', JSON.stringify([`W${s}${e}`]))
    }
    if (fn === 'cmo') {
      const v = cmo === '1' ? 1 : 0
      return wrap('changeCMO', `[${v}]`)
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
  }, [fn, consZone, consZoneFree, consTemp, ballon, airMode, modeSel, modeFree, customCode, vacStart, vacEnd, cmo, json, rpc])

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
            <option key={f.id} value={f.id}>{f.label}</option>
          ))}
        </select>
      </div>

      {fn === 'consigne' && (
        <ConsigneSection
          consZone={consZone} consZoneFree={consZoneFree} consTemp={consTemp}
          onZoneChange={setConsZone} onZoneFreeChange={setConsZoneFree} onTempChange={setConsTemp}
        />
      )}
      {fn === 'mode' && (
        <ModeSection
          modeSel={modeSel} modeFree={modeFree} customCode={customCode}
          onModeChange={setModeSel} onFreeChange={setModeFree} onCustomCodeChange={setCustomCode}
        />
      )}
      {fn === 'ballon' && <BallonSection ballon={ballon} onBallonChange={setBallon} />}
      {fn === 'air' && <AirSection airMode={airMode} onAirModeChange={setAirMode} />}
      {fn === 'vacances' && (
        <VacancesSection
          vacStart={vacStart} vacEnd={vacEnd}
          onStartChange={setVacStart} onEndChange={setVacEnd}
        />
      )}
      {fn === 'cmo' && <CmoSection cmo={cmo} onCmoChange={setCmo} />}
      {fn === 'custom' && <CustomSection json={json} onJsonChange={setJson} />}

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
          <code className={theme === 'jour' ? styles.payloadJour : styles.payloadNuit}>
            {payload}
          </code>
        </div>
      )}

      {status && <div className={styles.status}>{status}</div>}
      {!connected && (
        <div className={styles.warn}>box non connectée — envoi impossible pour l'instant</div>
      )}
    </div>
  )
}
