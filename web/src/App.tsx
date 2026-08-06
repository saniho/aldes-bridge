import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSse } from './hooks/useSse'
import { getConfig, setMode, disconnect, clearHistory } from './api'
import type { Config, MsgEvent } from './types'
import StatusBar from './components/StatusBar'
import SendPanel from './components/SendPanel'
import MessageStream from './components/MessageStream'
import ModeDiagram from './components/ModeDiagram'
import StatsBar from './components/StatsBar'
import './App.css'

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const { events, connected: sseAlive } = useSse(true)
  const [theme, setTheme] = useState<'nuit' | 'jour'>(() => {
    return (localStorage.getItem('aldes-theme') as 'nuit' | 'jour') || 'nuit'
  })

  useEffect(() => {
    if (theme === 'jour') {
      document.documentElement.dataset.theme = 'jour'
    } else {
      delete document.documentElement.dataset.theme
    }
    localStorage.setItem('aldes-theme', theme)
  }, [theme])

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
    const cur = config?.mode ?? m
    const msg =
      m === 'bridge'
        ? `Passer en mode bridge ?\n\nLa box ne passera plus par le cloud Azure (chemin : box → bridge uniquement).`
        : `Passer en mode proxy ?\n\nLa box rejoindra à nouveau le cloud Azure via le bridge.`
    const hint = cur === m ? ` (déjà en mode ${m})` : ''
    if (!window.confirm(msg + hint)) return
    try {
      const r = await setMode(m)
      setConfig((c) => {
        if (!c) return c
        return { ...c, mode: r.mode }
      })
    } catch (e) {
      alert(`changement de mode impossible : ${(e as Error).message}`)
    }
  }, [config?.mode])

  const onDisconnect = useCallback(async () => {
    if (!window.confirm('Déconnecter la box ?\n\nToute connexion en cours sera coupée.')) return
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
        <div className="topRight">
          <button
            className="theme"
            onClick={() => setTheme((t) => (t === 'nuit' ? 'jour' : 'nuit'))}
            title={theme === 'nuit' ? 'Passer en mode jour' : 'Passer en mode nuit'}
          >
            {theme === 'nuit' ? '☀️ jour' : '🌙 nuit'}
          </button>
          <button className="clear" onClick={onClear}>
            vider
          </button>
        </div>
      </header>
      <StatusBar
        config={config}
        sseAlive={sseAlive}
        onMode={onMode}
        onDisconnect={onDisconnect}
      />
      <ModeDiagram
        mode={config?.mode ?? null}
        connected={config?.connected ?? false}
        clientId={config?.client_id ?? null}
      />
      <StatsBar
        messages={messages}
        connected={config?.connected ?? false}
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