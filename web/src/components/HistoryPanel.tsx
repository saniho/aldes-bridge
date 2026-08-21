import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { getHistoryKeys, getHistorySeries, getHistoryTable } from '../api'
import type { HistoryKey, HistoryPoint } from '../types'
import { FAMILY_ORDER, getKeyMeta } from '../historyLabels'
import styles from './HistoryPanel.module.css'

interface Props {
  historyDays?: number | null
}

const PERIODS = [
  { id: '24h', label: '24 h', hours: 24 },
  { id: '7j', label: '7 j', hours: 7 * 24 },
  { id: '30j', label: '30 j', hours: 30 * 24 },
  { id: '90j', label: '90 j', hours: 90 * 24 },
] as const

type PeriodId = (typeof PERIODS)[number]['id']

function fmtTs(epoch: number): string {
  const d = new Date(epoch * 1000)
  if (Number.isNaN(d.getTime())) return ''
  const parts = new Intl.DateTimeFormat('fr-FR', {
    timeZone: 'Europe/Paris',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d)
  const get = (t: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === t)?.value ?? ''
  return `${get('day')}/${get('month')} ${get('hour')}:${get('minute')}`
}

export default function HistoryPanel({ historyDays }: Props) {
  const [keys, setKeys] = useState<HistoryKey[]>([])
  const [key, setKey] = useState<string>('')
  const [period, setPeriod] = useState<PeriodId>('24h')
  const [mode, setMode] = useState<'graph' | 'table'>('graph')
  const [series, setSeries] = useState<HistoryPoint[]>([])
  const [table, setTable] = useState<{
    total: number
    samples: Array<{ ts: number; kind: string; key: string; value: number }>
  }>({ total: 0, samples: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadKeys = useCallback(async () => {
    try {
      const ks = await getHistoryKeys()
      setKeys(ks)
      setKey((cur) => cur || ks.find((k) => k.kind === 'telemetry')?.key || (ks[0]?.key ?? ''))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    loadKeys()
  }, [loadKeys])

  const span = useMemo(() => {
    const hours = PERIODS.find((p) => p.id === period)?.hours ?? 24
    const end = Date.now() / 1000
    return { start: end - hours * 3600, end }
  }, [period])

  const loadSeries = useCallback(async () => {
    if (!key) return
    setLoading(true)
    setError(null)
    try {
      const hours = PERIODS.find((p) => p.id === period)?.hours ?? 24
      // ~1 point par 10 min max : bucket adaptatif selon la periode
      const points = hours * 6
      const bucket = Math.max(1, Math.round((hours * 3600) / points))
      setSeries(await getHistorySeries(key, span.start, span.end, bucket))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [key, period, span])

  const loadTable = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await getHistoryTable(span.start, span.end, 500)
      setTable({ total: page.total, samples: page.samples })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [span])

  useEffect(() => {
    if (mode === 'graph') loadSeries()
    else loadTable()
  }, [mode, key, period, span, loadSeries, loadTable])

  const graphData = useMemo(
    () =>
      series.map((p) => ({
        ts: p.ts,
        label: fmtTs(p.ts),
        value:
          p.value !== undefined
            ? Number(p.value.toFixed(2))
            : p.avg !== undefined
              ? Number(p.avg.toFixed(2))
              : undefined,
      })),
    [series]
  )

  const groups = useMemo(() => {
    const famRank = new Map<string, number>(FAMILY_ORDER.map((f, i) => [f, i]))
    const map = new Map<string, HistoryKey[]>()
    for (const k of keys) {
      const family = getKeyMeta(k.key).family
      if (!map.has(family)) map.set(family, [])
      map.get(family)!.push(k)
    }
    return [...map.entries()].sort(
      (a, b) =>
        (famRank.get(a[0]) ?? FAMILY_ORDER.length) -
        (famRank.get(b[0]) ?? FAMILY_ORDER.length)
    )
  }, [keys])

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <div className={styles.title}>📊 Historique des valeurs</div>
        <div className={styles.sub}>
          {historyDays
            ? `Conservation : ${historyDays} jours (paramétrable via ALDES_HISTORY_DAYS)`
            : 'Historisation inactive'}
        </div>
        <div className={styles.row}>
          <select
            className={styles.sel}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            aria-label="Capteur"
          >
            <option value="" disabled>
              — capteur —
            </option>
            {groups.map(([family, ks]) => (
              <optgroup key={family} label={family}>
                {ks.map((k) => {
                  const meta = getKeyMeta(k.key)
                  return (
                    <option key={k.key} value={k.key}>
                      {k.key} — {meta.label}
                    </option>
                  )
                })}
              </optgroup>
            ))}
          </select>
          <div className={styles.seg}>
            {PERIODS.map((p) => (
              <button
                key={p.id}
                className={styles.segBtn + (period === p.id ? ' active' : '')}
                onClick={() => setPeriod(p.id)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className={styles.seg}>
            <button
              className={styles.segBtn + (mode === 'graph' ? ' active' : '')}
              onClick={() => setMode('graph')}
            >
              📈 graphique
            </button>
            <button
              className={styles.segBtn + (mode === 'table' ? ' active' : '')}
              onClick={() => setMode('table')}
            >
              📋 tableau
            </button>
          </div>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {mode === 'graph' ? (
        <div className={styles.chartBox}>
          {loading ? (
            <div className={styles.loading}>chargement…</div>
          ) : graphData.length === 0 ? (
            <div className={styles.empty}>aucune valeur sur cette période</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={graphData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="label"
                  interval="preserveStartEnd"
                  minTickGap={48}
                  tick={{ fontSize: 10, fill: 'var(--text-soft)' }}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: 'var(--text-soft)' }}
                  domain={['auto', 'auto']}
                  width={48}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-strong)',
                    color: 'var(--text)',
                    fontSize: 12,
                  }}
                  labelStyle={{ color: 'var(--text-soft)' }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="var(--accent, #2f6fed)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      ) : (
        <div className={styles.tableBox}>
          <div className={styles.sub}>
            {table.total} échantillons sur la période (500 plus récents affichés)
          </div>
          {table.samples.length === 0 ? (
            <div className={styles.empty}>aucune valeur sur cette période</div>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>date (Paris)</th>
                  <th>clé</th>
                  <th>type</th>
                  <th>valeur</th>
                </tr>
              </thead>
              <tbody>
                {table.samples.map((s, i) => (
                  <tr key={i}>
                    <td>{fmtTs(s.ts)}</td>
                    <td>{s.key}</td>
                    <td>{s.kind}</td>
                    <td>{Number(s.value.toFixed(2))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}