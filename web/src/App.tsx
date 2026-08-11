import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSse } from './hooks/useSse'
import { getConfig, setMode, disconnect, clearHistory, getLogs } from './api'
import type { BridgeEvent, Config, Mode, MsgEvent } from './types'
import StatusBar from './components/StatusBar'
import SendPanel from './components/SendPanel'
import MessageStream from './components/MessageStream'
import ModeDiagram from './components/ModeDiagram'
import StatsBar from './components/StatsBar'
import RawPanel from './components/RawPanel'
import CommandBuilder from './components/CommandBuilder'
import './App.css'

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const { events, connected: sseAlive } = useSse(true)
  const [theme, setTheme] = useState<'nuit' | 'jour'>(() => {
    return (localStorage.getItem('aldes-theme') as 'nuit' | 'jour') || 'nuit'
  })
  const [histOpen, setHistOpen] = useState(false)
  const [log, setLog] = useState<{
    events: BridgeEvent[]
    total: number
    offset: number
    loading: boolean
  }>({ events: [], total: 0, offset: 0, loading: false })

  const LOG_PAGE = 200

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

  const onMode = useCallback(async (m: Mode) => {
    const cur = config?.mode ?? m
    const msg =
      m === 'bridge'
        ? `Passer en mode bridge ?\n\nLa box ne passera plus par le cloud Azure (chemin : box → bridge uniquement).`
        : m === 'raw'
          ? `Passer en mode natif (broker) ?\n\nLe bridge se connectera en client MQTT au broker configuré (box <-> broker <-> bridge).`
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
      setLog({ events: [], total: 0, offset: 0, loading: false })
    } catch (e) {
      alert((e as Error).message)
    }
  }, [])

  const loadLog = useCallback(
    async (offset: number, mode: 'replace' | 'append') => {
      setLog((l) => ({ ...l, loading: true }))
      try {
        const page = await getLogs(LOG_PAGE, offset)
        setLog((l) => ({
          events: mode === 'append' ? [...l.events, ...page.events] : page.events,
          total: page.total,
          offset: offset + page.events.length,
          loading: false
        }))
      } catch (e) {
        setLog((l) => ({ ...l, loading: false }))
        alert(`historique indisponible : ${(e as Error).message}`)
      }
    },
    []
  )

  useEffect(() => {
    if (histOpen && log.events.length === 0 && !log.loading) loadLog(0, 'replace')
  }, [histOpen, log.events.length, log.loading, loadLog])

  const shown = useMemo<MsgEvent[]>(() => {
    if (!histOpen) return messages
    return log.events.filter((e): e is MsgEvent => e.kind === 'message')
  }, [histOpen, messages, log.events])

  return (
    <div className="app">
      <header className="top">
        <h1>Aldes Bridge</h1>
        <div className="topRight">
          <button
            className={'hist' + (histOpen ? ' active' : '')}
            onClick={() => {
              if (histOpen) setHistOpen(false)
              else setHistOpen(true)
            }}
            title={histOpen ? 'Revenir au flux en temps réel' : 'Consulter le log persistant (à posteriori)'}
          >
            {histOpen ? '⚡ temps réel' : '🕘 historique'}
          </button>
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
        <>
          <div className="streamCol">
            {histOpen && (
              <div className="histbar">
                <span className="histLabel">
                  🕘 historique — {log.events.length} trames affichées / {log.total} au total
                </span>
                <span className="histActions">
                  <button
                    disabled={log.loading || log.offset >= log.total}
                    onClick={() => loadLog(log.offset, 'append')}
                  >
                    {log.loading ? 'chargement…' : '↕ charger antérieur'}
                  </button>
                  <button disabled={log.loading || log.offset === 0} onClick={() => loadLog(0, 'replace')}>
                    ⤒ début
                  </button>
                </span>
              </div>
            )}
            <MessageStream messages={shown} />
          </div>
          <div className="side">
          <CommandBuilder
            mode={config?.mode ?? null}
            connected={config?.connected ?? false}
            clientId={config?.client_id ?? null}
            defaultTopic={config?.mode === 'raw' ? config?.raw?.cmd_topic ?? null : null}
          />
          <SendPanel
            mode={config?.mode ?? null}
            connected={config?.connected ?? false}
            clientId={config?.client_id ?? null}
            defaultTopic={config?.mode === 'raw' ? config?.raw?.cmd_topic ?? null : null}
          />
          {config?.mode === 'raw' && <RawPanel />}
          </div>
        </>
      </div>
    </div>
  )
}