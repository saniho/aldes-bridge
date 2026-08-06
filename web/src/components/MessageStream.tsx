import { useEffect, useMemo, useRef, useState } from 'react'
import type { MsgEvent } from '../types'
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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return messages.filter((m) => {
      if (dir !== 'all' && m.direction !== dir) return false
      if (type !== 'all' && m.type !== type) return false
      if (injectedOnly && !m.injected) return false
      if (!q) return true
      const hay = [m.type, LABEL[m.type] ?? '', m.topic ?? '', m.payload ?? '']
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [messages, search, dir, type, injectedOnly])

  useEffect(() => {
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [filtered])

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.legend}>
          <span className={styles.in}>▲ box → cloud</span>
          <span className={styles.out}>▼ cloud → box</span>
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
      </div>
      <div className={styles.box} ref={boxRef}>
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
              <span className={styles.ts}>{m.ts}</span>
              <span className={styles.kind}>{LABEL[m.type] ?? m.type}</span>
              <span className={styles.dir}>{m.direction === 'out' ? 'box' : 'cloud'}</span>
              {m.injected && <span className={styles.badge}>INJECTÉ</span>}
              <span className={styles.qos}>{m.qos !== undefined ? `qos${m.qos}` : ''}</span>
            </div>
            {m.topic && <div className={styles.topic}>{m.topic}</div>}
            {m.payload && <pre className={styles.payload}>{m.payload}</pre>}
          </div>
        ))}
      </div>
    </div>
  )
}