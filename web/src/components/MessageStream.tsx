import { useEffect, useMemo, useRef, useState } from 'react'
import type { MsgEvent } from '../types'
import { fmtParis } from '../parisTime'
import styles from './MessageStream.module.css'

interface Props {
  messages: MsgEvent[]
}

const LABEL: Record<string, string> = {
  '1': 'CONNECT',
  '2': 'CONNACK',
  '3': 'PUBLISH',
  '4': 'PUBACK',
  '5': 'PUBREC',
  '6': 'PUBREL',
  '7': 'PUBCOMP',
  '8': 'SUBSCRIBE',
  '9': 'SUBACK',
  '10': 'UNSUBSCRIBE',
  '11': 'UNSUBACK',
  '12': 'PINGREQ',
  '13': 'PINGRESP',
  '14': 'DISCONNECT'
}

export default function MessageStream({ messages }: Props) {
  const boxRef = useRef<HTMLDivElement>(null)
  const [search, setSearch] = useState('')
  const [dir, setDir] = useState<'all' | 'in' | 'out'>('all')
  const [type, setType] = useState('all')
  const [injectedOnly, setInjectedOnly] = useState(false)
  const [follow, setFollow] = useState(true)
  const [nearBottom, setNearBottom] = useState(true)
  const [copied, setCopied] = useState<number | null>(null)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return messages.filter((m) => {
      if (dir !== 'all' && m.direction !== dir) return false
      if (type !== 'all' && m.type !== type) return false
      if (injectedOnly && !m.injected) return false
      if (!q) return true
      const hay = [m.type, LABEL[m.type] ?? '', m.topic ?? '', m.payload ?? '', String(m.session ?? ''), String(m.host ?? '')]
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [messages, search, dir, type, injectedOnly])

  const onScroll = () => {
    const el = boxRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 24
    setNearBottom(near)
    if (near) setFollow(true)
    else setFollow(false)
  }

  const jumpToBottom = () => {
    setFollow(true)
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  useEffect(() => {
    if (follow) {
      const el = boxRef.current
      if (el) el.scrollTop = el.scrollHeight
    }
  }, [filtered, follow])

  useEffect(() => {
    if (copied === null) return
    const t = setTimeout(() => setCopied(null), 1500)
    return () => clearTimeout(t)
  }, [copied])

  const copy = async (payload: string | null | undefined, i: number) => {
    if (!payload) return
    try {
      await navigator.clipboard.writeText(payload)
      setCopied(i)
    } catch {
      /* clipboard refusé — silencieux */
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.legend}>
          <span className={styles.in}>▲ box → cloud</span>
          <span className={styles.out}>▼ cloud → box</span>
        </span>
        <span className={styles.count}>
          {filtered.length} / {messages.length}
        </span>
      </div>
      <div className={styles.filters}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="rechercher…"
          spellCheck={false}
        />
        <select value={dir} onChange={(e) => setDir(e.target.value as 'all' | 'in' | 'out')}>
          <option value="all">tous sens</option>
          <option value="in">box → cloud</option>
          <option value="out">cloud → box</option>
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="all">tous types</option>
          {Object.values(LABEL).map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <label className={styles.ck}>
          <input
            type="checkbox"
            checked={injectedOnly}
            onChange={(e) => setInjectedOnly(e.target.checked)}
          />
          injections
        </label>
        <label className={styles.ck}>
          <input
            type="checkbox"
            checked={follow}
            onChange={(e) => setFollow(e.target.checked)}
          />
          suivre
        </label>
      </div>
      <div className={styles.box} ref={boxRef} onScroll={onScroll}>
        {filtered.length === 0 && <div className={styles.empty}>aucun message</div>}
        {filtered.map((m, i) => (
          <div
            key={i}
            className={
              styles.msg +
              ' ' +
              (m.direction === 'out' ? styles['out'] : styles['in']) +
              (m.injected ? ' ' + styles['injected'] : '')
            }
          >
            <div className={styles.head}>
              <span className={styles.ts} title="fuseau Paris">
                {fmtParis(m.ts)}
              </span>
              <span className={styles.kind}>{LABEL[m.type] ?? m.type}</span>
              <span className={styles.dir}>{m.direction === 'out' ? 'box' : 'cloud'}</span>
              {m.session !== undefined && m.session !== null && (
                <span className={styles.sess}>#{m.session}</span>
              )}
              {m.host && <span className={styles.host}>{m.host}</span>}
              {m.injected && <span className={styles.badge}>INJECTÉ</span>}
              <span className={styles.qos}>{m.qos !== undefined ? `qos${m.qos}` : ''}</span>
              {m.payload && (
                <button
                  className={styles.copyBtn}
                  onClick={() => copy(m.payload, i)}
                  title="copier le message"
                >
                  {copied === i ? 'copié ✓' : 'copier'}
                </button>
              )}
            </div>
            {m.topic && <div className={styles.topic}>{m.topic}</div>}
            {m.payload && (
              <pre
                className={styles.payload + (copied === i ? ' ' + styles.copied : '')}
                onClick={() => copy(m.payload, i)}
                title="copier"
              >
                {copied === i ? '📋 copié' : m.payload}
              </pre>
            )}
          </div>
        ))}
      </div>
      {!nearBottom && filtered.length > 0 && (
        <button className={styles.goto} onClick={jumpToBottom}>
          ↓ suivre
        </button>
      )}
    </div>
  )
}