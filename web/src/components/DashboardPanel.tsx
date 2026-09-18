import { useEffect, useState } from 'react'
import { getProducts } from '../api'
import type { AldesProduct, HealthData } from '../types'
import styles from './DashboardPanel.module.css'

interface Props {
  connected?: boolean
  health?: HealthData | null
}

function fmtDeg(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v.toFixed(1) + ' °C'
}

function fmtMode(code: string | null | undefined): { code: string; label: string; icon: string } {
  if (!code) return { code: '—', label: '', icon: '—' }
  const map: Record<string, { label: string; icon: string }> = {
    A: { label: 'Arrêt', icon: '⏹' },
    B: { label: 'Confort', icon: '🔥' },
    C: { label: 'Éco', icon: '🌿' },
    D: { label: 'Auto 1', icon: '⚡' },
    E: { label: 'Auto 2', icon: '⚡' },
    F: { label: 'Froid confort', icon: '❄️' },
    G: { label: 'Froid boost', icon: '❄️' },
    H: { label: 'Froid auto 1', icon: '❄️' },
    I: { label: 'Froid auto 2', icon: '❄️' },
    L: { label: 'ECS Arrêt', icon: '⏹' },
    M: { label: 'ECS Marche', icon: '💧' },
    N: { label: 'ECS Boost', icon: '💧' },
  }
  const m = map[code]
  return m ? { code, label: m.label, icon: m.icon } : { code, label: '', icon: '•' }
}

function fmtDefr(defr: number | null | undefined, mfac: number | null | undefined): { text: string; cls: string } {
  if (Number(mfac) === 0) return { text: 'N/A (clim off)', cls: '' }
  if (Number(defr) !== 0) return { text: 'ALERTE', cls: 'alert' }
  return { text: 'OK', cls: 'ok' }
}

function hasAlert(health: HealthData | null | undefined): boolean {
  if (!health) return false
  return !!(health.hpc && health.hpc !== 0) || fmtDefr(health.defr, health.mfac).cls === 'alert'
}

function tempColor(v: number | null | undefined): string {
  if (v === null || v === undefined) return ''
  if (v < 5) return styles.cold
  if (v < 18) return styles.cool
  if (v < 24) return styles.warm
  return styles.hot
}

export default function DashboardPanel({ connected, health }: Props) {
  const [products, setProducts] = useState<AldesProduct[]>([])
  const [now, setNow] = useState<number>(() => Date.now())

  useEffect(() => {
    let alive = true
    const poll = () => {
      getProducts().then((p) => { if (alive) setProducts(p) }).catch(() => {})
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15_000)
    return () => clearInterval(id)
  }, [])

  const product = products[0]
  const indicator = product?.indicator
  const temps = indicator?.thermostats ?? []
  const airMode = fmtMode(indicator?.current_air_mode)
  const waterMode = fmtMode(indicator?.current_water_mode)
  const defrStatus = fmtDefr(health?.defr, health?.mfac)
  const hpcAlert = health?.hpc && health.hpc !== 0
  const alertActive = hasAlert(health)
  const extTemp = health?.text_ext
  const ned = indicator?.qte_eau_chaude

  return (
    <div className={styles.panel}>
      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroMain}>
          <div className={styles.heroTemp + ' ' + tempColor(extTemp)}>
            {fmtDeg(extTemp)}
          </div>
          <div className={styles.heroMeta}>
            <span className={styles.heroLabel}>Extérieur</span>
            <span className={styles.heroSub}>
              {connected ? 'Box connectée' : 'Box déconnectée'}
            </span>
          </div>
        </div>
        <div className={styles.heroBadges}>
          <span className={styles.badge + ' ' + (connected ? styles.badgeOk : styles.badgeOff)}>
            {airMode.icon} {airMode.code} · {airMode.label}
          </span>
          <span className={styles.badge + ' ' + (health?.mfac && health.mfac !== 0 ? styles.badgeOk : styles.badgeOff)}>
            Compresseur {health?.mfac && health.mfac !== 0 ? 'ON' : 'OFF'}
          </span>
        </div>
      </div>

      {/* Alertes banner */}
      {alertActive && (
        <div className={styles.alertBanner}>
          <span className={styles.alertDot} />
          <span>
            {hpcAlert && 'Haute pression (HPC) — '}
            {defrStatus.cls === 'alert' && 'Défaut circuit froid (Defr)'}
          </span>
        </div>
      )}

      {/* Zones */}
      {temps.length > 0 && (
        <div className={styles.card}>
          <div className={styles.cardTitle}>Zones</div>
          <div className={styles.pills}>
            {temps.map((t, i) => (
              <div key={i} className={styles.pill + ' ' + tempColor(t.CurrentTemperature)}>
                <span className={styles.pillZone}>Zone {i}</span>
                <span className={styles.pillTemp}>{fmtDeg(t.CurrentTemperature)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ECS */}
      <div className={styles.card}>
        <div className={styles.cardTitle}>Eau chaude sanitaire</div>
        <div className={styles.ecsRow}>
          <div className={styles.progressWrap}>
            <div className={styles.progressLabel}>Niveau</div>
            <div className={styles.progressBar}>
              <div
                className={styles.progressFill + ' ' + (ned !== null && ned !== undefined && ned < 20 ? styles.progressLow : '')}
                style={{ width: `${ned ?? 0}%` }}
              />
            </div>
            <div className={styles.progressValue}>{ned ?? '—'} %</div>
          </div>
          <div className={styles.ecsMode}>
            <span className={styles.ecsModeLabel}>Mode</span>
            <span className={styles.ecsModeValue}>{waterMode.icon} {waterMode.code} · {waterMode.label}</span>
          </div>
        </div>
      </div>

      {/* Timestamp */}
      <div className={styles.timestamp}>
        Dernière mise à jour : {new Date(now).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  )
}
