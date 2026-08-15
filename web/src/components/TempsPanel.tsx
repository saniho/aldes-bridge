import { useEffect, useMemo, useState } from 'react'
import { getProducts, sendCommand } from '../api'
import type { AldesProduct, MsgEvent } from '../types'
import { fmtParis } from '../parisTime'
import styles from './TempsPanel.module.css'

interface Props {
  pollMs?: number
  clientId?: string | null
  connected?: boolean
  messages?: MsgEvent[]
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

function parseRequested(messages: MsgEvent[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const m of messages) {
    const p = m.payload
    if (!p) continue
    const mm = p.match(/"method"\s*:\s*"changeConsigneC(\d{1,2})"\s*,\s*"params"\s*:\s*\["([^"]+)"\]/)
    if (!mm) continue
    const v = parseFloat(mm[2])
    if (!Number.isNaN(v)) map[mm[1]] = v
  }
  return map
}

/** Détecte les mises à jour de température envoyées par la box (non-injectées) */
function parseBoxTemps(messages: MsgEvent[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const m of messages) {
    if (m.injected) continue
    const p = m.payload
    if (!p) continue
    const mm = p.match(/"UsC(\d{1,2})"\s*:\s*([0-9.]+)/)
    if (!mm) continue
    const v = parseFloat(mm[2])
    if (!Number.isNaN(v)) map[mm[1]] = v
  }
  return map
}

export default function TempsPanel({ pollMs = 5000, clientId, connected, messages }: Props) {
  const [products, setProducts] = useState<AldesProduct[]>([])
  const [error, setError] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [requested, setRequested] = useState<Record<string, number>>({})
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({})
  const [sending, setSending] = useState<string | null>(null)

  const requestedFromSse = useMemo(() => parseRequested(messages ?? []), [messages])
  const boxTemps = useMemo(() => parseBoxTemps(messages ?? []), [messages])

  useEffect(() => {
    setRequested((r) => ({ ...r, ...requestedFromSse }))
  }, [requestedFromSse])

  useEffect(() => {
    if (Object.keys(boxTemps).length === 0) return
    setConfirmed((c) => {
      const next = { ...c }
      for (const [zone, val] of Object.entries(boxTemps)) {
        const req = requestedFromSse[zone]
        if (req !== undefined && Math.abs(req - val) < 0.01) {
          next[zone] = true
        }
      }
      return next
    })
  }, [boxTemps, requestedFromSse])

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

  const canSend = !!connected && !!clientId

  const step = async (t: { ThermostatId: string; TemperatureSet: number | null; CurrentTemperature: number | null }, delta: number) => {
    if (!canSend) return
    const zone = 'C' + t.ThermostatId
    const base = t.TemperatureSet ?? t.CurrentTemperature ?? 0
    const next = Math.round((base + delta) * 2) / 2
    const val = Number.isInteger(next) ? String(next) : next.toFixed(1)
    const payload = JSON.stringify({ id: 1, jsonrpc: '2.0', method: `changeConsigne${zone}`, params: [val] })
    setSending(zone)
    try {
      await sendCommand(`devices/${clientId}/messages/devicebound`, payload, 1)
      setRequested((r) => ({ ...r, [t.ThermostatId]: next }))
      setConfirmed((c) => ({ ...c, [t.ThermostatId]: false }))
    } catch (e) {
      alert(`échec envoi ${zone} : ${(e as Error).message}`)
    } finally {
      setSending(null)
    }
  }

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
                {ts.map((t) => {
                  const req = requested[t.ThermostatId]
                  const isPending = req !== undefined && !confirmed[t.ThermostatId]
                  return (
                    <tr key={t.ThermostatId}>
                      <td className={styles.zone}>{t.Name}</td>
                      <td className={styles.reel}>{fmtDeg(t.CurrentTemperature)}</td>
                      <td className={styles.consigne}>
                        <div className={styles.consigneRow}>
                          <button
                            className={styles.stepBtn}
                            onClick={() => step(t, -1)}
                            disabled={!canSend || sending !== null}
                            title="Diminuer de 1 °C"
                          >
                            −
                          </button>
                          <span className={styles.consigneVal}>{fmtDeg(t.TemperatureSet)}</span>
                          <button
                            className={styles.stepBtn}
                            onClick={() => step(t, 1)}
                            disabled={!canSend || sending !== null}
                            title="Augmenter de 1 °C"
                          >
                            +
                          </button>
                        </div>
                        {isPending && (
                          <div className={styles.pending}>
                            demandé {fmtDeg(req, 1)}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
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
