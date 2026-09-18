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

function fmtMode(code: string | null | undefined): string {
  if (!code) return '—'
  const labels: Record<string, string> = {
    A: 'Arrêt', B: 'Confort', C: 'Éco', D: 'Auto 1', E: 'Auto 2',
    F: 'Froid confort', G: 'Froid boost', H: 'Froid auto 1', I: 'Froid auto 2',
    L: 'ECS Arrêt', M: 'ECS Marche', N: 'ECS Boost'
  }
  const label = labels[code]
  return label ? `${code} · ${label}` : code
}

function fmtDefr(defr: number | null | undefined, mfac: number | null | undefined): { text: string; cls: string } {
  const compressorOff = Number(mfac) === 0
  if (compressorOff) return { text: 'N/A (clim off)', cls: '' }
  if (Number(defr) !== 0) return { text: 'ALERTE', cls: 'alert' }
  return { text: 'OK', cls: 'ok' }
}

export default function DashboardPanel({ connected, health }: Props) {
  const [products, setProducts] = useState<AldesProduct[]>([])

  useEffect(() => {
    let alive = true
    const poll = () => {
      getProducts().then((p) => { if (alive) setProducts(p) }).catch(() => {})
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const product = products[0]
  const indicator = product?.indicator
  const temps = indicator?.thermostats ?? []

  const defrStatus = fmtDefr(health?.defr, health?.mfac)
  const hpcAlert = health?.hpc && health.hpc !== 0

  return (
    <div className={styles.panel}>
      <div className={styles.card}>
        <div className={styles.cardTitle}>Statut</div>
        <div className={styles.grid}>
          <div className={styles.indicator}>
            <span className={styles.label}>Box Aldes</span>
            <span className={styles.value + ' ' + (connected ? ' ' + styles.ok : '')}>
              <span className={'dot ' + (connected ? styles.dotOk : styles.dotAlert)} />
              {connected ? 'Connectée' : 'Déconnectée'}
            </span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Mode</span>
            <span className={styles.value}>{fmtMode(product?.indicator?.current_air_mode)}</span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Compresseur</span>
            <span className={styles.value + ' ' + (health?.mfac && health.mfac !== 0 ? ' ' + styles.ok : '')}>
              {health?.mfac && health.mfac !== 0 ? 'Marche' : 'Arrêt'}
            </span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Extérieur</span>
            <span className={styles.value + ' ' + styles.big}>{fmtDeg(health?.text_ext)}</span>
          </div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Alertes</div>
        <div className={styles.alerts}>
          <div className={styles.statusRow + ' ' + (hpcAlert ? ' ' + styles.alertRow : ' ' + styles.okRow)}>
            <span className={'dot ' + (hpcAlert ? styles.dotAlert : styles.dotOk)} />
            <span className={styles.statusLabel}>Haute pression (HPC)</span>
            <span className={styles.statusValue + ' ' + (hpcAlert ? ' ' + styles.alert : '')}>
              {hpcAlert ? 'ALERTE' : 'Normal'}
            </span>
          </div>
          <div className={styles.statusRow + ' ' + (defrStatus.cls === 'alert' ? ' ' + styles.alertRow : ' ' + styles.okRow)}>
            <span className={'dot ' + (defrStatus.cls === 'alert' ? styles.dotAlert : styles.dotOk)} />
            <span className={styles.statusLabel}>Circuit froid (Defr)</span>
            <span className={styles.statusValue + ' ' + (defrStatus.cls === 'alert' ? ' ' + styles.alert : '')}>
              {defrStatus.text}
            </span>
          </div>
        </div>
      </div>

      {temps.length > 0 && (
        <div className={styles.card}>
          <div className={styles.cardTitle}>Températures zones</div>
          <div className={styles.zonesGrid}>
            {temps.map((t, i) => (
              <div key={i} className={styles.zoneItem}>
                <span className={styles.zoneLabel}>Zone {i}</span>
                <span className={styles.zoneValue}>{fmtDeg(t.CurrentTemperature)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className={styles.card}>
        <div className={styles.cardTitle}>Eau chaude</div>
        <div className={styles.grid}>
          <div className={styles.indicator}>
            <span className={styles.label}>Niveau (NED)</span>
            <span className={styles.value + ' ' + styles.big}>{product?.indicator?.qte_eau_chaude ?? '—'} %</span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Mode eau</span>
            <span className={styles.value}>{fmtMode(product?.indicator?.current_water_mode)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
