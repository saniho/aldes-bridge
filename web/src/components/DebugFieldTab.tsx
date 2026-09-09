import { useState, useCallback } from 'react'
import { getFieldValues } from '../api'
import type { FieldValue } from '../types'
import { fmtParis } from '../parisTime'
import styles from './DebugPanel.module.css'

const PERIODS = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7j', hours: 168 },
]

export default function DebugFieldTab() {
  const [field, setField] = useState('')
  const [period, setPeriod] = useState(24)
  const [results, setResults] = useState<FieldValue[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const LIMIT = 200

  const search = useCallback(async (off = 0) => {
    if (!field.trim()) return
    setLoading(true)
    setError('')
    try {
      const end = Date.now() / 1000
      const start = end - period * 3600
      const res = await getFieldValues({
        field: field.trim(),
        start,
        end,
        limit: LIMIT,
        offset: off,
      })
      setResults(res.samples)
      setTotal(res.total)
      setOffset(off)
    } catch (e: any) {
      setError(e.message || 'Erreur de recherche')
    } finally {
      setLoading(false)
    }
  }, [field, period])

  const handleSearch = () => search(0)
  const handleNext = () => search(offset + LIMIT)
  const handlePrev = () => search(Math.max(0, offset - LIMIT))

  const formatValue = (v: number | string | boolean) => {
    if (typeof v === 'number') return v % 1 === 0 ? String(v) : v.toFixed(1)
    return String(v)
  }

  return (
    <div className={styles.fieldTab}>
      <div className={styles.searchRow}>
        <input
          className={styles.searchInput}
          type="text"
          value={field}
          onChange={e => setField(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="Nom du champ (ex: MT0, UAM, productid)..."
        />
        <select
          className={styles.select}
          value={period}
          onChange={e => setPeriod(Number(e.target.value))}
        >
          {PERIODS.map(p => (
            <option key={p.hours} value={p.hours}>{p.label}</option>
          ))}
        </select>
        <button
          className={styles.btn}
          onClick={handleSearch}
          disabled={loading || !field.trim()}
        >
          {loading ? '...' : 'Rechercher'}
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {total > 0 && (
        <div className={styles.resultInfo}>
          {total} valeur{total > 1 ? 's' : ''} pour « {field} » — affichage {offset + 1}–{Math.min(offset + LIMIT, total)}
        </div>
      )}

      {results.length > 0 && (
        <table className={styles.fieldTable}>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Valeur</th>
              <th>Source → Destination</th>
            </tr>
          </thead>
          <tbody>
            {results.map((sample, idx) => (
              <tr key={idx}>
                <td className={styles.tsCell}>{fmtParis(new Date(sample.ts * 1000).toISOString())}</td>
                <td className={styles.valueCell}>{formatValue(sample.value)}</td>
                <td>
                  <span className={styles.badge + ' ' + styles[`src_${sample.source}`] || ''}>
                    {sample.source} → {sample.destination}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {results.length === 0 && !loading && !error && field.trim() && (
        <div className={styles.empty}>Aucune valeur trouvée pour « {field} »</div>
      )}

      {total > LIMIT && (
        <div className={styles.pagination}>
          <button className={styles.btn} onClick={handlePrev} disabled={offset === 0}>
            « Précédent
          </button>
          <span className={styles.pageInfo}>
            {Math.floor(offset / LIMIT) + 1}/{Math.ceil(total / LIMIT)}
          </span>
          <button
            className={styles.btn}
            onClick={handleNext}
            disabled={offset + LIMIT >= total}
          >
            Suivant »
          </button>
        </div>
      )}
    </div>
  )
}
