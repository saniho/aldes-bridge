import { useEffect, useState } from 'react'
import { getProducts, sendCommand, requestConsigne } from '../api'
import type { AldesProduct, DeviceMode, DeviceProfile, VentilationData } from '../types'
import { fmtParis } from '../parisTime'
import styles from './TempsPanel.module.css'

interface Props {
  pollMs?: number
  clientId?: string | null
  connected?: boolean
  consignes?: Record<string, { requested: number; confirmed: boolean; attempts?: number; ts?: string }>
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

function modesOfField(profile: DeviceProfile | null | undefined, field: string): DeviceMode[] {
  switch (field) {
    case 'air_modes_clim':
      return profile?.air_modes_clim ?? []
    case 'air_modes_heat':
      return profile?.air_modes_heat ?? []
    case 'air_modes':
      return profile?.air_modes ?? []
    case 'water_modes':
      return profile?.water_modes ?? []
    default:
      return []
  }
}

const QUICK_GROUP_LABELS: Record<string, string> = {
  air_modes_clim: 'Climatisation',
  air_modes_heat: 'Chauffage',
  air_modes: 'Air',
  water_modes: 'ECS',
}

interface QuickGroup {
  field: string
  label: string
  water: boolean
  modes: { code: string; label: string }[]
}

// Repli historique utilise uniquement quand aucun profil n'est charge
// (installation sans profil, ou API sans champ profile).
const LEGACY_QUICK_GROUPS: QuickGroup[] = [
  {
    field: 'air_modes_clim',
    label: 'Climatisation',
    water: false,
    modes: [
      { code: 'F', label: 'F · Confort' }, { code: 'G', label: 'G · Boost' },
      { code: 'H', label: 'H · Programme C' }, { code: 'I', label: 'I · Programme D' },
      { code: 'A', label: 'A · Off' },
    ],
  },
  {
    field: 'air_modes_heat',
    label: 'Chauffage',
    water: false,
    modes: [
      { code: 'B', label: 'B · Confort' }, { code: 'C', label: 'C · Éco' },
      { code: 'D', label: 'D · Programme A' }, { code: 'E', label: 'E · Programme B' },
      { code: 'A', label: 'A · Off' },
    ],
  },
  {
    field: 'water_modes',
    label: 'ECS',
    water: true,
    modes: [{ code: 'M', label: 'M · On' }, { code: 'L', label: 'L · Off' }],
  },
]

function buildQuickGroups(profile: DeviceProfile | null | undefined): QuickGroup[] {
  if (!profile) return LEGACY_QUICK_GROUPS

  const defs = profile.ui?.quick_modes?.length
    ? profile.ui.quick_modes
    : Object.keys(QUICK_GROUP_LABELS)
        .filter((field) => modesOfField(profile, field).length > 0)
        .map((field) => ({ field, label: QUICK_GROUP_LABELS[field] }))

  return defs
    .map((def) => {
      const modes = modesOfField(profile, def.field)
      return {
        field: def.field,
        label: def.label || QUICK_GROUP_LABELS[def.field] || def.field,
        water: def.field === 'water_modes',
        modes: modes.map((m) => ({ code: m.code, label: `${m.code} · ${m.label}` })),
      }
    })
    .filter((group) => group.modes.length > 0)
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
  const QUICK_GROUPS = buildQuickGroups(profile)
  const showThermostats = profile?.ui?.show_thermostats !== false
  const showHotWater = profile?.ui?.show_hot_water !== false

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
              {QUICK_GROUPS.map((group) => (
                <div key={group.field} className={styles.quick}>
                  <span className={styles.quickLabel}>{group.label}</span>
                  {group.modes.map((q) => {
                    const current = group.water
                      ? p.indicator.current_water_mode
                      : p.indicator.current_air_mode
                    return (
                      <button
                        key={group.field + '-' + q.code}
                        className={styles.quickBtn + (current === q.code ? ' ' + styles.active : '')}
                        onClick={() => quickMode(q.code, group.water)}
                        disabled={!canSend || sending !== null}
                        title={`changeMode ["${q.code}"]`}
                      >
                        {q.label}
                      </button>
                    )
                  })}
                </div>
              ))}
            </div>

            <div className={styles.stats}>
              {showThermostats && (
                <div className={styles.stat}>
                  <span className={styles.statLabel}>Temp. principale</span>
                  <span className={styles.statValue + ' ' + styles.big}>
                    {fmtDeg(p.indicator.tmp_principal)}
                  </span>
                </div>
              )}
              {showHotWater && (
                <>
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
                </>
              )}
              <div className={styles.stat}>
                <span className={styles.statLabel}>Mode air</span>
                <span className={styles.statValue}>
                  {fmtMode(p.indicator.current_air_mode, AIR_LABEL)}
                </span>
              </div>
              {showHotWater && (
                <div className={styles.stat}>
                  <span className={styles.statLabel}>Mode ECS</span>
                  <span className={styles.statValue}>
                    {fmtMode(p.indicator.current_water_mode, WATER_LABEL)}
                  </span>
                </div>
              )}
              {p.indicator.hors_gel && (
                <div className={styles.stat + ' ' + styles.gel}>
                  <span className={styles.statLabel}>Hors gel</span>
                  <span className={styles.statValue}>actif</span>
                </div>
              )}
              {p.indicator.antilegionelles && (
                <div className={styles.stat + ' ' + styles.gel}>
                  <span className={styles.statLabel}>Anti-légionelles</span>
                  <span className={styles.statValue}>actif</span>
                </div>
              )}
            </div>

            {showThermostats && (
              <>
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
                                {(entry.attempts ?? 0) > 0 && (
                                  <span> (tentative {entry.attempts}/2)</span>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </>
            )}

            {p.indicator.ventilation && (() => {
              const v = p.indicator.ventilation as VentilationData
              const hasData = v.rvei != null || v.dno != null || v.dma != null || v.dint != null || v.dln != null || v.dple != null || v.dmco != null
              if (!hasData) return null
              return (
                <>
                  <div className={styles.tableTitle}>Ventilation</div>
                  <div className={styles.stats}>
                    {v.rvei != null && (
                      <div className={styles.stat}>
                        <span className={styles.statLabel}>Ventilateur</span>
                        <span className={styles.statValue}>
                          {v.rvei} <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>tr/min</span>
                        </span>
                      </div>
                    )}
                    {v.dno != null && (
                      <div className={styles.stat}>
                        <span className={styles.statLabel}>Debit nominal</span>
                        <span className={styles.statValue}>
                          {v.dno} <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>m&sup3;/h</span>
                        </span>
                      </div>
                    )}
                    {v.dma != null && (
                      <div className={styles.stat}>
                        <span className={styles.statLabel}>Debit max</span>
                        <span className={styles.statValue}>
                          {v.dma} <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>m&sup3;/h</span>
                        </span>
                      </div>
                    )}
                    {v.dint != null && (
                      <div className={styles.stat}>
                        <span className={styles.statLabel}>Debit intermediaire</span>
                        <span className={styles.statValue}>
                          {v.dint} <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>m&sup3;/h</span>
                        </span>
                      </div>
                    )}
                    {v.dln != null && (
                      <div className={styles.stat}>
                        <span className={styles.statLabel}>Debit nuit</span>
                        <span className={styles.statValue}>
                          {v.dln} <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>m&sup3;/h</span>
                        </span>
                      </div>
                    )}
                    {v.dple != null && (
                      <div className={styles.stat}>
                        <span className={styles.statLabel}>Debit plein</span>
                        <span className={styles.statValue}>
                          {v.dple} <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>m&sup3;/h</span>
                        </span>
                      </div>
                    )}
                    {v.dmco != null && (
                      <div className={styles.stat}>
                        <span className={styles.statLabel}>Debit max CO2</span>
                        <span className={styles.statValue}>
                          {v.dmco} <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>m&sup3;/h</span>
                        </span>
                      </div>
                    )}
                  </div>
                </>
              )
            })()}

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
