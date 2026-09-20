import { useEffect, useState } from 'react'
import { getProducts } from '../api'
import type { AldesProduct, AldesThermostat, Config, HealthData } from '../types'
import styles from './DashboardPanel.module.css'

interface Props {
  config?: Config | null
  connected?: boolean
  health?: HealthData | null
}

/* ── helpers ── */

function deg(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(1)
}

function pct(v: number | null | undefined): string {
  return v == null ? '—' : String(Math.round(v))
}

function airLabel(code: string | null | undefined): string {
  if (!code) return '—'
  const m: Record<string, string> = {
    A: 'Arrêt', B: 'Confort', C: 'Éco', D: 'Auto A', E: 'Auto B',
    F: 'Froid confort', G: 'Froid boost', H: 'Froid A', I: 'Froid B',
  }
  return m[code] ?? code
}

function waterLabel(code: string | null | undefined): string {
  if (!code) return '—'
  const m: Record<string, string> = { L: 'Arrêt', M: 'Marche', N: 'Boost' }
  return m[code] ?? code
}

function compressorOn(mfac: number | null | undefined): boolean {
  return mfac != null && mfac !== 0
}

function tempClass(v: number | null | undefined): string {
  if (v == null) return ''
  if (v < 5) return styles.cold
  if (v < 18) return styles.cool
  if (v < 24) return styles.warm
  return styles.hot
}

function zoneName(t: AldesThermostat, i: number): string {
  if (t.Name && t.Name !== t.ThermostatId) return t.Name
  return `Zone ${i + 1}`
}

function fmtDur(since: number | null | undefined, now: number): string {
  if (!since) return '—'
  const s = Math.max(0, Math.floor(now / 1000 - since))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}min`
  return `${Math.floor(s / 3600)}h${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}`
}

/* ── component ── */

export default function DashboardPanel({ config, connected, health }: Props) {
  const [products, setProducts] = useState<AldesProduct[]>([])
  const [now, setNow] = useState(() => Date.now())
  const [sysOpen, setSysOpen] = useState(false)

  useEffect(() => {
    let alive = true
    const poll = () => { getProducts().then((p) => { if (alive) setProducts(p) }).catch(() => {}) }
    poll()
    const id = setInterval(poll, 5000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15_000)
    return () => clearInterval(id)
  }, [])

  const ind = products[0]?.indicator
  const zones = ind?.thermostats ?? []
  const extTemp = health?.text_ext
  const extHum = zones[0]?.CurrentHumidity
  const coOn = compressorOn(health?.mfac)

  const mfacVal = health?.mfac
  const defrVal = health?.defr
  const hpcVal = health?.hpc

  const compressorOff = mfacVal == null || Number(mfacVal) === 0
  const hpc = !compressorOff && hpcVal != null && Number(hpcVal) !== 0
  const defr = !compressorOff && defrVal != null && Number(defrVal) !== 0
  const alertOn = hpc || defr
  const ned = ind?.qte_eau_chaude

  const avgTemp = zones.length > 0
    ? zones.reduce((s, z) => s + (z.CurrentTemperature ?? 0), 0) / zones.filter((z) => z.CurrentTemperature != null).length
    : null

  return (
    <div className={styles.dash}>
      {/* ── 1. Header ── */}
      <header className={styles.header}>
        <h1 className={styles.title}>Aldes Bridge</h1>
        <span className={connected ? styles.badgeOk : styles.badgeOff}>
          <span className={connected ? styles.dotGreen : styles.dotRed} />
          {connected ? 'Connectée' : 'Hors ligne'}
        </span>
      </header>

      {/* ── 2. Alertes ── */}
      {alertOn && (
        <div className={styles.alert}>
          <span className={styles.alertIcon}>!</span>
          <span className={styles.alertText}>
            {hpc && 'Pression circuit haute'}
            {hpc && defr && ' · '}
            {defr && 'Défaut dégivrage'}
          </span>
        </div>
      )}

      {/* ── 3. Actions rapides ── */}
      <div className={styles.actions}>
        <button className={styles.btnAction} type="button" disabled={!connected}>
          <span className={styles.btnIcon}>⏻</span>
          <span className={styles.btnLabel}>Arrêt</span>
        </button>
        <button
          className={styles.btnAction + ' ' + (coOn ? styles.btnActive : '')}
          type="button"
          disabled={!connected}
        >
          <span className={styles.btnIcon}>⚙</span>
          <span className={styles.btnLabel}>Compresseur</span>
          <span className={styles.btnState}>{coOn ? 'Marche' : 'Arrêt'}</span>
        </button>
      </div>

      {/* ── 4. Extérieur ── */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Extérieur</div>
        <div className={styles.twoCol}>
          <div className={styles.statCard}>
            <span className={styles.statLabel}>Température</span>
            <span className={styles.statValue + ' ' + tempClass(extTemp)}>
              {deg(extTemp)}<span className={styles.unit}>°C</span>
            </span>
          </div>
          <div className={styles.statCard}>
            <span className={styles.statLabel}>Humidité</span>
            <span className={styles.statValue}>
              {pct(extHum)}<span className={styles.unit}>%</span>
            </span>
          </div>
        </div>
      </div>

      {/* ── 5. Zones ── */}
      {zones.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Zones climatisées</div>
          <div className={styles.zoneGrid}>
            {zones.map((z, i) => (
              <div key={z.ThermostatId || i} className={styles.zoneCell}>
                <span className={styles.zoneName}>{zoneName(z, i)}</span>
                <span className={styles.zoneTemp + ' ' + tempClass(z.CurrentTemperature)}>
                  {deg(z.CurrentTemperature)}°
                </span>
              </div>
            ))}
            {zones.length > 1 && avgTemp != null && (
              <div className={styles.zoneCell + ' ' + styles.zoneAvg}>
                <span className={styles.zoneName}>Moyenne</span>
                <span className={styles.zoneTemp}>{deg(avgTemp)}°</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 6. Eau chaude ── */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Eau chaude</div>
        <div className={styles.ecsBar}>
          <div className={styles.progressTrack}>
            <div
              className={styles.progressFill + (ned != null && ned < 20 ? ' ' + styles.progressLow : '')}
              style={{ width: `${ned ?? 0}%` }}
            />
          </div>
          <span className={styles.ecsPct}>{pct(ned)}%</span>
        </div>
        <div className={styles.ecsMeta}>
          <span className={styles.ecsMode}>Mode : {waterLabel(ind?.current_water_mode)}</span>
          <span className={styles.ecsMode}>Ventilation : {airLabel(ind?.current_air_mode)}</span>
        </div>
      </div>

      {/* ── 7. Infos système ── */}
      <div className={styles.sysSection}>
        <button className={styles.sysToggle} type="button" onClick={() => setSysOpen(!sysOpen)}>
          <span>Infos système</span>
          <span className={styles.sysArrow + (sysOpen ? ' ' + styles.sysArrowOpen : '')}>▸</span>
        </button>
        {sysOpen && (
          <div className={styles.sysGrid}>
            <div className={styles.sysRow}>
              <span className={styles.sysLabel}>Box</span>
              <span className={styles.sysVal}>{fmtDur(config?.box_since, now)}</span>
            </div>
            <div className={styles.sysRow}>
              <span className={styles.sysLabel}>Azure</span>
              <span className={styles.sysVal}>{fmtDur(config?.cloud_since, now)}</span>
            </div>
            <div className={styles.sysRow}>
              <span className={styles.sysLabel}>Mode</span>
              <span className={styles.sysVal}>{config?.mode ?? '—'}</span>
            </div>
            <div className={styles.sysRow}>
              <span className={styles.sysLabel}>Version</span>
              <span className={styles.sysVal}>{config?.server_version ?? '—'}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
