import { useEffect, useState } from 'react'
import { getProducts } from '../api'
import type { AldesProduct } from '../types'
import { fmtParis } from '../parisTime'
import styles from './TempsPanel.module.css'

interface Props {
  pollMs?: number
}

const AIR_LABEL: Record<string, string> = {
  A: 'Arrêt',
  B: 'Confort',
  C: 'Éco',
  D: 'Auto 1',
  E: 'Auto 2',
  F: 'Froid confort',
  G: 'Froid boost',
  H: 'Froid auto 1',
  I: 'Froid auto 2'
}

const WATER_LABEL: Record<string, string> = {
  L: 'Arrêt',
  M: 'Marche',
  N: 'Boost'
}

function fmtDeg(v: number | null, digits = 1): string {
  return v === null || v === undefined ? '—' : v.toFixed(digits) + ' °C'
}

function fmtMode(code: string | null, water: boolean): string {
  if (!code) return '—'
  const label = (water ? WATER_LABEL : AIR_LABEL)[code]
  return label ? `${code} · ${label}` : code
}

function fmtStamp(iso: string): string {
  const s = fmtParis(iso)
  return s ? `${s} (Paris)` : ''
}

function ballonMode(code: string | null): { label: string; on: boolean } | null {
  if (!code) return null
  const m = WATER_LABEL[code]
  if (!m) return null
  return { label: m, on: code !== 'L' }
}

export default function TempsPanel({ pollMs = 5000 }: Props) {
  const [products, setProducts] = useState<AldesProduct[]>([])
  const [error, setError] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setInterval> | null = null
    const poll = async () => {
      try {
        const p = await getProducts()
        if (!alive) return
        setProducts(p)
        setError(null)
        setFailed(false)
      } catch (e) {
        if (!alive) return
        setError((e as Error).message)
        setFailed(true)
      }
    }
    poll()
    timer = setInterval(poll, pollMs)
    return () => {
      alive = false
      if (timer) clearInterval(timer)
    }
  }, [pollMs])

  if (failed && products.length === 0) {
    return (
      <div className={styles.panel}>
        <div className={styles.warn}>API Aldes injoignable : {error}</div>
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      {products.length === 0 && (
        <div className={styles.empty}>
          Aucune télémetrie pour l'instant — en attente des données de la box
          (le bridge republie la dernière trame connue).
        </div>
      )}
      {products.map((p) => {
        const ts = p.indicator.thermostats
        return (
          <div key={p.serial_number} className={styles.card}>
            <div className={styles.cardHead}>
              <div>
                <div className={styles.name}>{p.name}</div>
                <div className={styles.sub}>
                  {p.modem} · {p.serial_number} · {p.reference}
                </div>
              </div>
              <span
                className={styles.badge + ' ' + (p.isConnected ? styles.on : styles.off)}
              >
                {p.isConnected ? '● connectée' : '○ hors ligne'}
              </span>
            </div>

            <div className={styles.stats}>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Temp. principale</span>
                <span className={styles.statValue + ' ' + styles.big}>
                  {fmtDeg(p.indicator.tmp_principal)}
                </span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Eau chaude (ECS)</span>
                <span className={styles.statValue}>
                  {p.indicator.qte_eau_chaude === null || p.indicator.qte_eau_chaude === undefined
                    ? '—'
                    : `${p.indicator.qte_eau_chaude} %`}
                </span>
              </div>
              {(() => {
                const b = ballonMode(p.indicator.current_water_mode)
                return (
                  <div className={styles.stat + (b && b.on ? ' ' + styles.ballonOn : '')}>
                    <span className={styles.statLabel}>Ballon</span>
                    <span className={styles.statValue}>
                      {b ? (b.on ? 'On' : 'Off') : '—'}
                      {b && <span className={styles.ballonMode}>&nbsp;· {b.label}</span>}
                    </span>
                  </div>
                )
              })()}
              <div className={styles.stat}>
                <span className={styles.statLabel}>Mode air</span>
                <span className={styles.statValue}>
                  {fmtMode(p.indicator.current_air_mode, false)}
                </span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Mode ECS</span>
                <span className={styles.statValue}>
                  {fmtMode(p.indicator.current_water_mode, true)}
                </span>
              </div>
              {p.indicator.hors_gel && (
                <div className={styles.stat + ' ' + styles.gel}>
                  <span className={styles.statLabel}>Hors gel</span>
                  <span className={styles.statValue}>actif</span>
                </div>
              )}
            </div>

            <div className={styles.tableTitle}>Thermostats</div>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Réel</th>
                  <th>Consigne</th>
                </tr>
              </thead>
              <tbody>
                {ts.length === 0 && (
                  <tr>
                    <td colSpan={3} className={styles.none}>
                      aucune zone connue
                    </td>
                  </tr>
                )}
                {ts.map((t) => (
                  <tr key={t.ThermostatId}>
                    <td className={styles.zone}>{t.Name}</td>
                    <td className={styles.reel}>{fmtDeg(t.CurrentTemperature)}</td>
                    <td className={styles.consigne}>{fmtDeg(t.TemperatureSet)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className={styles.foot}>
              {p.updatedAt ? (
                <>
                  <span>mise à jour : {fmtStamp(p.updatedAt)}</span>
                  {p.lastUpdatedDate && (
                    <span className={styles.trame} title="horodatage dt fourni par la box">
                      trame box : {fmtStamp(p.lastUpdatedDate)}
                    </span>
                  )}
                </>
              ) : (
                'pas encore de données'
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}