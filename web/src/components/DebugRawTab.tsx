import { useState, useCallback } from 'react'
import { searchRawMessages } from '../api'
import type { DebugMessage } from '../types'
import { fmtParis } from '../parisTime'
import styles from './DebugPanel.module.css'

const PERIODS = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7j', hours: 168 },
]

const SOURCES = ['', 'box', 'azure', 'webui', 'ha', 'bridge', 'broker']
const DESTINATIONS = ['', 'box', 'azure', 'ha', 'broker', 'bridge']

export default function DebugRawTab() {
  const [text, setText] = useState('')
  const [period, setPeriod] = useState(24)
  const [source, setSource] = useState('')
  const [destination, setDestination] = useState('')
  const [results, setResults] = useState<DebugMessage[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const LIMIT = 50

  const search = useCallback(async (off = 0) => {
    if (!text.trim()) return
    setLoading(true)
    setError('')
    try {
      const end = Date.now() / 1000
      const start = end - period * 3600
      const res = await searchRawMessages({
        text: text.trim(),
        start,
        end,
        source: source || undefined,
        destination: destination || undefined,
        limit: LIMIT,
        offset: off,
      })
      setResults(res.messages)
      setTotal(res.total)
      setOffset(off)
    } catch (e: any) {
      setError(e.message || 'Erreur de recherche')
    } finally {
      setLoading(false)
    }
  }, [text, period, source, destination])

  const handleSearch = () => search(0)
  const handleNext = () => search(offset + LIMIT)
  const handlePrev = () => search(Math.max(0, offset - LIMIT))

  const toggleExpand = (idx: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const renderPayload = (payload: string) => {
    try {
      const obj = JSON.parse(payload)
      return JSON.stringify(obj, null, 2)
    } catch {
      return payload
    }
  }

  const srcDstLabel = (src: string, dst: string) => `${src} → ${dst}`

  return (
    <div className={styles.rawTab}>
      <div className={styles.searchRow}>
        <input
          className={styles.searchInput}
          type="text"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="Rechercher dans les messages..."
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
        <select
          className={styles.select}
          value={source}
          onChange={e => setSource(e.target.value)}
        >
          <option value="">Toutes sources</option>
          {SOURCES.filter(Boolean).map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          className={styles.select}
          value={destination}
          onChange={e => setDestination(e.target.value)}
        >
          <option value="">Toutes destinations</option>
          {DESTINATIONS.filter(Boolean).map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <button
          className={styles.btn}
          onClick={handleSearch}
          disabled={loading || !text.trim()}
        >
          {loading ? '...' : 'Rechercher'}
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {total > 0 && (
        <div className={styles.resultInfo}>
          {total} résultat{total > 1 ? 's' : ''} — affichage {offset + 1}–{Math.min(offset + LIMIT, total)}
        </div>
      )}

      <div className={styles.messageList}>
        {results.map((msg, idx) => (
          <div
            key={idx}
            className={styles.messageCard + (msg.source === 'ha' ? ' ' + styles.fromHa : '')}
          >
            <div
              className={styles.messageHeader}
              onClick={() => toggleExpand(idx)}
            >
              <span className={styles.expandIcon}>{expanded.has(idx) ? '▼' : '▶'}</span>
              <span className={styles.timestamp}>{fmtParis(new Date(msg.ts * 1000).toISOString())}</span>
              <span className={styles.badge + ' ' + styles[`src_${msg.source}`] || ''}>
                {srcDstLabel(msg.source, msg.destination)}
              </span>
            </div>
            {expanded.has(idx) && (
              <pre className={styles.payload}>
                {renderPayload(msg.payload)}
              </pre>
            )}
          </div>
        ))}
      </div>

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
