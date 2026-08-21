import { ZONES, MODES, dateInputValue } from './commandBuilderData'
import styles from './SendPanel.module.css'

interface CommonProps {
  onChange?: () => void
}

interface ConsigneProps extends CommonProps {
  consZone: string
  consZoneFree: boolean
  consTemp: string
  onZoneChange: (v: string) => void
  onZoneFreeChange: (v: boolean) => void
  onTempChange: (v: string) => void
}

export function ConsigneSection({ consZone, consZoneFree, consTemp, onZoneChange, onZoneFreeChange, onTempChange }: ConsigneProps) {
  return (
    <>
      <div className={styles.row}>
        <label>Zone</label>
        <select
          value={consZoneFree ? '__free' : consZone}
          onChange={(e) => {
            if (e.target.value === '__free') {
              onZoneFreeChange(true)
            } else {
              onZoneFreeChange(false)
              onZoneChange(e.target.value)
            }
          }}
        >
          {ZONES.map((z) => (
            <option key={z.id} value={z.id}>{z.label}</option>
          ))}
          <option value="__free">Personnalisé…</option>
        </select>
        {consZoneFree && (
          <input
            value={consZone}
            onChange={(e) => onZoneChange(e.target.value)}
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
          onChange={(e) => onTempChange(e.target.value)}
        />
      </div>
      <div className={styles.hint}>
        <span>
          <code>changeConsigneC0..C9</code> · params en chaîne <code>{'["21"]'}</code> — format
          réellement utilisé par le cloud Aldes (C0 = zone principale)
        </span>
      </div>
    </>
  )
}

interface ModeProps extends CommonProps {
  modeSel: string
  modeFree: boolean
  customCode: string
  onModeChange: (v: string) => void
  onFreeChange: (v: boolean) => void
  onCustomCodeChange: (v: string) => void
}

export function ModeSection({ modeSel, modeFree, customCode, onModeChange, onFreeChange, onCustomCodeChange }: ModeProps) {
  return (
    <>
      <div className={styles.row}>
        <label>Mode</label>
        <select
          value={modeFree ? '__free' : modeSel}
          onChange={(e) => {
            if (e.target.value === '__free') {
              onFreeChange(true)
              onCustomCodeChange('')
            } else {
              onFreeChange(false)
              onModeChange(e.target.value)
            }
          }}
        >
          {MODES.map((m) => (
            <option key={m.code} value={m.code}>{m.label}</option>
          ))}
          <option value="__free">Personnalisé…</option>
        </select>
      </div>
      {modeFree && (
        <div className={styles.row}>
          <label>Code</label>
          <input
            value={customCode}
            onChange={(e) => onCustomCodeChange(e.target.value)}
            placeholder="ex. V, X, W…"
            spellCheck={false}
          />
        </div>
      )}
    </>
  )
}

interface BallonProps extends CommonProps {
  ballon: string
  onBallonChange: (v: string) => void
}

export function BallonSection({ ballon, onBallonChange }: BallonProps) {
  return (
    <>
      <div className={styles.row}>
        <label>Ballon eau chaude</label>
        <select value={ballon} onChange={(e) => onBallonChange(e.target.value)}>
          <option value="on">On · production d'eau chaude</option>
          <option value="off">Off · arrêt</option>
        </select>
      </div>
      <div className={styles.hint}>
        <span>
          envoie <code>changeMode</code> <code>{'["M"]'}</code> (On) ou <code>{'["L"]'}</code> (Off)
        </span>
      </div>
    </>
  )
}

interface AirProps extends CommonProps {
  airMode: string
  onAirModeChange: (v: string) => void
}

export function AirSection({ airMode, onAirModeChange }: AirProps) {
  return (
    <>
      <div className={styles.row}>
        <label>Rafraîchissement air</label>
        <select value={airMode} onChange={(e) => onAirModeChange(e.target.value)}>
          <option value="B">B · Confort</option>
          <option value="C">C · Éco</option>
          <option value="D">D · Auto 1</option>
          <option value="E">E · Auto 2</option>
          <option value="F">F · Froid confort</option>
          <option value="G">G · Froid boost</option>
          <option value="H">H · Froid auto 1</option>
          <option value="I">I · Froid auto 2</option>
          <option value="A">A · Arrêt</option>
        </select>
      </div>
      <div className={styles.hint}>
        <span>
          envoie <code>changeMode</code> avec le code sélectionné (ex: <code>{'["B"]'}</code> confort, <code>{'["C"]'}</code> éco, <code>{'["A"]'}</code> arrêt)
        </span>
      </div>
    </>
  )
}

interface VacancesProps extends CommonProps {
  vacStart: string
  vacEnd: string
  onStartChange: (v: string) => void
  onEndChange: (v: string) => void
}

export function VacancesSection({ vacStart, vacEnd, onStartChange, onEndChange }: VacancesProps) {
  return (
    <>
      <div className={styles.row}>
        <label>Début</label>
        <input type="datetime-local" value={vacStart} onChange={(e) => onStartChange(e.target.value)} />
      </div>
      <div className={styles.row}>
        <label>Fin</label>
        <input type="datetime-local" value={vacEnd} onChange={(e) => onEndChange(e.target.value)} />
      </div>
      <div className={styles.hint}>
        <button
          type="button"
          onClick={() => {
            const now = new Date()
            const later = new Date(now.getTime() + 7 * 86400000)
            onStartChange(dateInputValue(now))
            onEndChange(dateInputValue(later))
          }}
        >
          +7 jours
        </button>
        <span>envoie <code>W…Z…Z</code> (UTC)</span>
      </div>
    </>
  )
}

interface CmoProps extends CommonProps {
  cmo: string
  onCmoChange: (v: string) => void
}

export function CmoSection({ cmo, onCmoChange }: CmoProps) {
  return (
    <div className={styles.row}>
      <label>Valeur</label>
      <select value={cmo} onChange={(e) => onCmoChange(e.target.value)}>
        <option value="1">1 · ON (override)</option>
        <option value="0">0 · OFF</option>
      </select>
    </div>
  )
}

interface CustomProps extends CommonProps {
  json: string
  onJsonChange: (v: string) => void
}

export function CustomSection({ json, onJsonChange }: CustomProps) {
  return (
    <div className={styles.row}>
      <label>JSON</label>
      <textarea
        value={json}
        onChange={(e) => onJsonChange(e.target.value)}
        rows={4}
        spellCheck={false}
        placeholder='{"method":"...","params":[...]}'
      />
    </div>
  )
}
