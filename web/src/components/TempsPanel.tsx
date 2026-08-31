import { useEffect, useState } from 'react'
import { getProducts, sendCommand, requestConsigne } from '../api'
import type { AldesProduct, DeviceMode, DeviceProfile } from '../types'
import { fmtParis } from '../parisTime'
import styles from './TempsPanel.module.css'

interface Props {
  pollMs?: number
  clientId?: string | null
  connected?: boolean
  consignes?: Record<string, { requested: number; confirmed: boolean; ts?: string }>
  profile?: DeviceProfile | null
}

function buildAirLabel(profile: DeviceProfile | null | undefined): Record<string, string> {
  const all = [
    ...(profile?.air_modes_clim ?? []),
    ...(profile?.air_modes_heat ?? []),
    ...(profile?.air_modes ?? []),
  ]
  if (all.length) {
    return Object.fromEntries(all.map((m) => [m.code, m.label]))
  }
  return {
    A: 'Arrêt', B: 'Confort', C: 'Éco', D: 'Auto 1', E: 'Auto 2',
    F: 'Froid confort', G: 'Froid boost', H: 'Froid auto 1', I: 'Froid auto 2'
  }
}

function buildWaterLabel(profile: DeviceProfile | null | undefined): Record<string, string> {
  if (profile?.water_modes?.length) {
    return Object.fromEntries(profile.water_modes.map((m) => [m.code, m.label]))
  }
  return { L: 'Arrêt', M: 'Marche', N: 'Boost' }
}

function buildQuickAirGroup(modes: DeviceMode[] | undefined, fallback: { code: string; label: string }[]): { code: string; label: string }[] {
  if (modes?.length) {
    return modes.map((m) => ({
      code: m.code, label: `${m.code} · ${m.label}`
    }))
  }
  return fallback
}

function buildQuickClim(profile: DeviceProfile | null | undefined): { code: string; label: string }[] {
  return buildQuickAirGroup(profile?.air_modes_clim, [
    { code: 'F', label: 'F · Confort' }, { code: 'D', label: 'D · Boost' },
    { code: 'H', label: 'H · Programme C' }, { code: 'I', label: 'I · Programme D' },
    { code: 'A', label: 'A · Off' },
  ])
}

function buildQuickHeat(profile: DeviceProfile | null | undefined): { code: string; label: string }[] {
  return buildQuickAirGroup(profile?.air_modes_heat, [
    { code: 'B', label: 'B · Confort' }, { code: 'C', label: 'C · Éco' },
    { code: 'D', label: 'D · Programme A' }, { code: 'E', label: 'E · Programme B' },
    { code: 'A', label: 'A · Off' },
  ])
}

function buildQuickWater(profile: DeviceProfile | null | undefined): { code: string; label: string }[] {
  if (profile?.water_modes?.length) {
    return profile.water_modes.map((m) => ({
      code: m.code, label: `${m.code} · ${m.label}`
    }))
  }
  return [{ code: 'M', label: 'M · On' }, { code: 'L', label: 'L · Off' }]
}

function fmtDeg(v: number | null, digits = 1): string {
  return v === null || v === undefined ? '—' : v.toFixed(digits) + ' °C'
}

function fmtMode(code: string | null, labels: Record<string, string>): string {
  if (!code) return '—'
  const label = labels[code]
  return label ? `${code} · ${label}` : code
}

function fmtStamp(iso: string): string {
  const s = fmtParis(iso)
  return s ? `${s} (Paris)` : ''
}

const FRESH_MIN = 15
const WATCH_MIN = 45

type Freshness = 'fresh' | 'watch' | 'stale'

function ageMin(iso: string | null | undefined, now: number): number | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.floor((now - t) / 60000))
}

function fmtAge(min: number): string {
  if (min < 1) return "moins d'1 min"
  if (min < 60) return `${min} min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m ? `${h} h ${m.toString().padStart(2, '0')}` : `${h} h`
}

function freshness(min: number): Freshness {
  if (min <= FRESH_MIN) return 'fresh'
  if (min <= WATCH_MIN) return 'watch'
  return 'stale'
}

function ballonMode(code: string | null, waterLabels: Record<string, string>): { label: string; on: boolean } | null {
  if (!code) return null
  const m = waterLabels[code]
  if (!m) return null
  return { label: m, on: code !== 'L' }
}

export default function TempsPanel({ pollMs = 5000, clientId, connected, consignes = {}, profile }: Props) {
  const [products, setProducts] = useState<AldesProduct[]>([])
  const [error, setError] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [sending, setSending] = useState<string | null>(null)
  const [now, setNow] = useState<number>(() => Date.now())

  const AIR_LABEL = buildAirLabel(profile)
  const WATER_LABEL = buildWaterLabel(profile)
  const QUICK_CLIM = buildQuickClim(profile)
  const QUICK_HEAT = buildQuickHeat(profile)
  const QUICK_WATER = buildQuickWater(profile)

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15_000)
    return () => clearInterval(id)
  }, [])

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
      await requestConsigne(t.ThermostatId, next)
    } catch (e) {
      alert(`échec envoi ${zone} : ${(e as Error).message}`)
    } finally {
      setSending(null)
    }
  }

  const quickMode = async (code: string, water: boolean) => {
    if (!canSend) return
    const key = (water ? 'w:' : 'a:') + code
    const payload = JSON.stringify({ id: 1, jsonrpc: '2.0', method: 'changeMode', params: [code] })
    setSending(key)
    try {
      await sendCommand(`devices/${clientId}/messages/devicebound`, payload, 1)
    } catch (e) {
      alert(`échec envoi ${key} : ${(e as Error).message}`)
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
              <div className={styles.cardHeadRight}>
                <span
                  className={
                    styles.badge +
                    ' ' +
                    (p.isConnected ? styles.on : styles.off)
                  }
                >
                  {p.isConnected ? '● connectée' : '○ hors ligne'}
                </span>
                {(() => {
                  const min = ageMin(p.updatedAt, now)
                  if (min === null) return null
                  const f = freshness(min)
                  return (
                    <span
                      className={styles.badge + ' ' + styles[f]}
                      title={`dernière trame reçue à ${fmtStamp(p.updatedAt ?? '')}`}
                    >
                      {f === 'stale'
                        ? `figée depuis ${fmtAge(min)}`
                        : f === 'watch'
                          ? `sans données depuis ${fmtAge(min)}`
                          : `à jour · ${fmtAge(min)}`}
                    </span>
                  )
                })()}
              </div>
            </div>

            <div className={styles.quickGroup}>
              {QUICK_CLIM.length > 0 && (
                <div className={styles.quick}>
                  <span className={styles.quickLabel}>Climatisation</span>
                  {QUICK_CLIM.map((q) => (
                    <button
                      key={q.code}
                      className={
                        styles.quickBtn +
                        (p.indicator.current_air_mode === q.code ? ' ' + styles.active : '')
                      }
                      onClick={() => quickMode(q.code, false)}
                      disabled={!canSend || sending !== null}
                      title={`changeMode ["${q.code}"]`}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              )}
              {QUICK_HEAT.length > 0 && (
                <div className={styles.quick}>
                  <span className={styles.quickLabel}>Chauffage</span>
                  {QUICK_HEAT.map((q) => (
                    <button
                      key={q.code}
                      className={
                        styles.quickBtn +
                        (p.indicator.current_air_mode === q.code ? ' ' + styles.active : '')
                      }
                      onClick={() => quickMode(q.code, false)}
                      disabled={!canSend || sending !== null}
                      title={`changeMode ["${q.code}"]`}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              )}
              {QUICK_CLIM.length === 0 && QUICK_HEAT.length > 0 && (
                <div className={styles.quick}>
                  <span className={styles.quickLabel}>Air</span>
                  {QUICK_HEAT.map((q) => (
                    <button
                      key={q.code}
                      className={
                        styles.quickBtn +
                        (p.indicator.current_air_mode === q.code ? ' ' + styles.active : '')
                      }
                      onClick={() => quickMode(q.code, false)}
                      disabled={!canSend || sending !== null}
                      title={`changeMode ["${q.code}"]`}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              )}
              <div className={styles.quick}>
                <span className={styles.quickLabel}>ECS</span>
                {QUICK_WATER.map((q) => (
                  <button
                    key={q.code}
                    className={
                      styles.quickBtn +
                      (p.indicator.current_water_mode === q.code ? ' ' + styles.active : '')
                    }
                    onClick={() => quickMode(q.code, true)}
                    disabled={!canSend || sending !== null}
                    title={`changeMode ["${q.code}"]`}
                  >
                    {q.label}
                  </button>
                ))}
              </div>
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
                const b = ballonMode(p.indicator.current_water_mode, WATER_LABEL)
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
                  {fmtMode(p.indicator.current_air_mode, AIR_LABEL)}
                </span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Mode ECS</span>
                <span className={styles.statValue}>
                  {fmtMode(p.indicator.current_water_mode, WATER_LABEL)}
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
                  const entry = consignes[t.ThermostatId]
                  const isPending = entry !== undefined && !entry.confirmed
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
                            demandé {fmtDeg(entry.requested, 1)}
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
