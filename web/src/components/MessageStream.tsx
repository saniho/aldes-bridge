import { useEffect, useRef } from 'react'
import type { MsgEvent } from '../types'
import styles from './MessageStream.module.css'

interface Props {
  messages: MsgEvent[]
}

const CLS: Record<string, string> = {
  '1': 'in',
  '2': 'in',
  '3': 'out'
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
  11: 'UNSUBACK',
  12: 'PINGREQ',
  13: 'PINGRESP',
  14: 'DISCONNECT'
}

export default function MessageStream({ messages }: Props) {
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.legend}>
          <span className={styles.in}>▲ vers cloud</span>
          <span className={styles.out}>▼ vers box</span>
        </span>
      </div>
      <div className={styles.box} ref={boxRef}>
        {messages.length === 0 && <div className={styles.empty}>aucun message</div>}
        {messages.map((m, i) => (
          <div key={i} className={styles.msg + ' ' + styles[CLS[m.type] ?? 'in']}>
            <div className={styles.head}>
              <span className={styles.ts}>{m.ts}</span>
              <span className={styles.kind}>{LABEL[m.type] ?? m.type}</span>
              <span className={styles.dir}>{CLS[m.type] === 'out' ? 'box' : 'cloud'}</span>
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