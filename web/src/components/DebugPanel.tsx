import { useState } from 'react'
import DebugRawTab from './DebugRawTab'
import DebugFieldTab from './DebugFieldTab'
import styles from './DebugPanel.module.css'

type Tab = 'raw' | 'field'

export default function DebugPanel() {
  const [tab, setTab] = useState<Tab>('raw')

  return (
    <div className={styles.panel}>
      <div className={styles.tabs}>
        <button
          className={styles.tab + (tab === 'raw' ? ' ' + styles.active : '')}
          onClick={() => setTab('raw')}
        >
          Messages bruts
        </button>
        <button
          className={styles.tab + (tab === 'field' ? ' ' + styles.active : '')}
          onClick={() => setTab('field')}
        >
          Valeurs du champ
        </button>
      </div>
      <div className={styles.content}>
        {tab === 'raw' && <DebugRawTab />}
        {tab === 'field' && <DebugFieldTab />}
      </div>
    </div>
  )
}
