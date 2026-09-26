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

function fmtTemp(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  return `${val} °C`
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

type StatusTone = 'ok' | 'warn' | 'muted'

function fmtDefr(defr: number | null | undefined, mfac: number | null | undefined): { text: string; tone: StatusTone } {
  if (mfac === 0) return { text: 'N/A (clim off)', tone: 'muted' }
  if (defr === null || defr === undefined) return { text: 'Inconnu', tone: 'muted' }
  if (defr === 0) return { text: 'Inactif', tone: 'ok' }
  if (defr === 1) return { text: 'Actif', tone: 'warn' }
  return { text: `Valeur inattendue (${defr})`, tone: 'muted' }
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

  const hpcActive = health.hpc != null && health.hpc !== 0
  const defrStatus = fmtDefr(health.defr, health.mfac)
  const defrRowTone = defrStatus.tone === 'ok' ? styles.ok : defrStatus.tone === 'warn' ? styles.warn : styles.muted
  const defrValueTone = defrStatus.tone === 'ok' ? styles.ok : defrStatus.tone === 'warn' ? styles.warn : styles.muted
  const defrDotTone = defrStatus.tone === 'ok' ? styles.dotOk : defrStatus.tone === 'warn' ? styles.dotWarn : styles.dotMuted

  const advancedTemps: { key: keyof HealthData; label: string }[] = [
    { key: 'tain', label: 'Air entrée' },
    { key: 'tahl', label: 'Éch. air — bas' },
    { key: 'tahu', label: 'Éch. air — haut' },
    { key: 'tehg', label: 'Éch. gaz' },
    { key: 'tehl', label: 'Éch. liquide' },
    { key: 'tehu', label: 'Éch. haut' },
    { key: 'tueh', label: 'Unité ext.' },
    { key: 'thga', label: 'Gaine air' },
  ]

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
        <div className={styles.cardTitle}>Environnement</div>
        <div className={styles.grid}>
          <div className={styles.indicator}>
            <span className={styles.label}>Temp. extérieure (Text)</span>
            <span className={styles.value + ' ' + styles.big}>
              {health.text_ext != null ? `${health.text_ext} °C` : '—'}
            </span>
          </div>
          <div className={styles.indicator}>
            <span className={styles.label}>Ventilateur (RVeI)</span>
            <span className={styles.value}>
              {health.rvei != null ? `${health.rvei} tr/min` : '—'}
            </span>
          </div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Températures avancées</div>
        <div className={styles.grid}>
          {advancedTemps.map(({ key, label }) => (
            <div key={key} className={styles.indicator}>
              <span className={styles.label}>{label}</span>
              <span className={styles.value}>{fmtTemp(health[key])}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardTitle}>Alertes</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div className={styles.statusRow + ' ' + (hpcActive ? styles.alert : styles.ok)}>
            <span className={'dot ' + (hpcActive ? styles.dotAlert : styles.dotOk)} />
            <span className={styles.statusLabel}>Haute pression compresseur (HPC)</span>
            <span className={styles.statusValue + ' ' + (hpcActive ? styles.alert : styles.ok)}>
              {hpcActive ? 'ALERTE' : 'Normal'}
            </span>
          </div>
          <div className={styles.statusRow + ' ' + defrRowTone}>
            <span className={'dot ' + defrDotTone} />
            <span className={styles.statusLabel}>Dégivrage (Defr)</span>
            <span className={styles.statusValue + ' ' + defrValueTone}>
              {defrStatus.text}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
