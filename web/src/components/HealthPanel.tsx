import type { HealthData } from '../types'
import styles from './HealthPanel.module.css'

interface Props {
  health: HealthData | null | undefined
}

function fmtBar(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  return `${val.toFixed(1)} bar`
}

function fmtRaw(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  return String(val)
}

function mfacLabel(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  return val === 0 ? 'Arrêt' : 'Marche'
}

function mfecLabel(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  if (val === 0) return 'Arrêt'
  if (val === 1) return 'Marche'
  if (val === 2) return 'Boost'
  return String(val)
}

function fmtDefr(defr: number | null | undefined, uam: number | null | undefined): { text: string; cls: string } {
  const climOff = uam === 0
  if (climOff) return { text: 'N/A (clim off)', cls: '' }
  if (defr && defr !== 0) return { text: 'ALERTE', cls: 'alert' }
  return { text: 'Pas de défaut', cls: 'ok' }
}

export default function HealthPanel({ health }: Props) {
  if (!health || Object.keys(health).length === 0) {
    return (
      <div className={styles.panel}>
        <div className={styles.empty}>
          Aucune donnée de santé pour l'instant — en attente des données de la box
        </div>
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      <div className={styles.card}>
        <div className={styles.cardTitle}>État compresseur</div>
        <div className={styles.grid}>
          <div className={styles.indicator}>
            <span className={styles.label}>Compresseur (MfAc)</span>
            <span className={styles.value + ' ' + (health.mfac && health.mfac !== 0 ? styles.ok : '')}>
              {mfacLabel(health.mfac)}
            </span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Mode eau (MfEc)</span>
            <span className={styles.value}>{mfecLabel(health.mfec)}</span>
          </div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Pressions circuit</div>
        <div className={styles.grid}>
          <div className={styles.indicator}>
            <span className={styles.label}>Pression haute (PreH)</span>
            <span className={styles.value + ' ' + styles.big}>{fmtBar(health.preh)}</span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Delta haut (dHi)</span>
            <span className={styles.value}>{fmtRaw(health.dhi)}</span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Delta bas (dLo)</span>
            <span className={styles.value}>{fmtRaw(health.dlo)}</span>
          </div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Alertes</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div className={styles.statusRow + ' ' + (health.hpc && health.hpc !== 0 ? ' ' + styles.alert : ' ' + styles.ok)}>
            <span className={'dot ' + (health.hpc && health.hpc !== 0 ? styles.dotAlert : styles.dotOk)} />
            <span className={styles.statusLabel}>Haute pression compresseur (HPC)</span>
            <span className={styles.statusValue + ' ' + (health.hpc && health.hpc !== 0 ? styles.alert : styles.ok)}>
              {health.hpc && health.hpc !== 0 ? 'ALERTE' : 'Normal'}
            </span>
          </div>
          <div className={styles.statusRow + ' ' + (fmtDefr(health.defr, health.uam).cls === 'alert' ? ' ' + styles.alert : ' ' + styles.ok)}>
            <span className={'dot ' + (fmtDefr(health.defr, health.uam).cls === 'alert' ? styles.dotAlert : styles.dotOk)} />
            <span className={styles.statusLabel}>Défaut circuit froid (Defr)</span>
            <span className={styles.statusValue + ' ' + (fmtDefr(health.defr, health.uam).cls === 'alert' ? styles.alert : styles.ok)}>
              {fmtDefr(health.defr, health.uam).text}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
