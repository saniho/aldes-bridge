import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSse } from './hooks/useSse'
import { getConfig, setMode, disconnect, clearHistory } from './api'
import type { Config, MsgEvent } from './types'
import StatusBar from './components/StatusBar'
import SendPanel from './components/SendPanel'
import MessageStream from './components/MessageStream'
import './App.css'

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const { events, connected: sseAlive } = useSse(true)

  useEffect(() => {
    getConfig().then((cfg) => {
      setConfig({
        mode: cfg.mode,
        connected: false,
        client_id: null,
        topics: []
      })
    }).catch(() => {})
  }, [])

const { messages, lastSnapshot } = useMemo(() => {
    const messages: MsgEvent[] = []
    let lastSnapshot: Config | null = null
    for (const e of events) {
      if (e.kind === 'snapshot') {
        lastSnapshot = e.config
        messages.push(...e.messages)
      } else if (e.kind === 'message') {
        messages.push(e)
      }
    }
    return { messages, lastSnapshot }
  }, [events])

  useEffect(() => {
    if (lastSnapshot) setConfig(lastSnapshot)
  }, [lastSnapshot])

  const onMode = useCallback(async (m: 'proxy' | 'bridge') => {
    try {
      const r = await setMode(m)
      setConfig((c) => {
        if (!c) return c
        return { ...c, mode: r.mode }
      })
    } catch (e) {
      alert(`changement de mode impossible : ${(e as Error).message}`)
    }
  }, [])

  const onDisconnect = useCallback(async () => {
    try {
      await disconnect()
    } catch (e) {
      alert((e as Error).message)
    }
  }, [])

  const onClear = useCallback(async () => {
    try {
      await clearHistory()
    } catch (e) {
      alert((e as Error).message)
    }
  }, [])

  return (
    <div className="app">
      <header className="top">
        <h1>Aldes Bridge</h1>
        <button className="clear" onClick={onClear}>
          vider
        </button>
      </header>
      <StatusBar
        config={config}
        sseAlive={sseAlive}
        onMode={onMode}
        onDisconnect={onDisconnect}
      />
      <div className="layout">
        <MessageStream messages={messages} />
        <SendPanel
          mode={config?.mode ?? null}
          connected={config?.connected ?? false}
          clientId={config?.client_id ?? null}
        />
      </div>
    </div>
  )
}