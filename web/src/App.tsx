import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSse } from './hooks/useSse'
import { getConfig, setMode, disconnect, clearHistory, getLogs } from './api'
import type { BridgeEvent, Config, Mode, MsgEvent } from './types'
import StatusBar from './components/StatusBar'
import MessageStream from './components/MessageStream'
import ModeDiagram from './components/ModeDiagram'
import StatsBar from './components/StatsBar'
import RawPanel from './components/RawPanel'
import CommandBuilder from './components/CommandBuilder'
import TempsPanel from './components/TempsPanel'
import WrapperPanel from './components/WrapperPanel'
import './App.css'

type View = 'temps' | 'commande' | 'log' | 'wrapper'

const TABS: { id: View; label: string; title: string }[] = [
  { id: 'temps', label: '🌡 températures', title: 'Températures / infos de la PAC' },
  { id: 'commande', label: '📤 commande', title: 'Envoyer des commandes à la box' },
  { id: 'log', label: '📜 log', title: 'Trames MQTT en temps réel et historique' },
  { id: 'wrapper', label: '🔌 wrapper', title: 'Appels API du bridge (test interactif)' }
]

export default function App() {
  const [config, setConfig] = useState<Config | null>(null)
  const { events, connected: sseAlive } = useSse(true)
  const [theme, setTheme] = useState<'nuit' | 'jour'>(() => {
    return (localStorage.getItem('aldes-theme') as 'nuit' | 'jour') || 'nuit'
  })
  const [view, setView] = useState<View>(() => {
    const stored = localStorage.getItem('aldes-view')
    if (stored === 'flux') return 'log'
    if (stored === 'temps' || stored === 'commande' || stored === 'log' || stored === 'wrapper') {
      return stored
    }
    return 'log'
  })
  const [histOpen, setHistOpen] = useState(false)
  const [requested, setRequested] = useState<Record<string, number>>({})
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({})
  const [log, setLog] = useState<{
    events: BridgeEvent[]
    total: number
    offset: number
    loading: boolean
  }>({ events: [], total: 0, offset: 0, loading: false })

  const LOG_PAGE = 200

  const parseRequested = useCallback((msgs: MsgEvent[]): Record<string, number> => {
    const map: Record<string, number> = {}
    for (const m of msgs) {
      const p = m.payload
      if (!p) continue
      const mm = p.match(/"method"\s*:\s*"changeConsigneC(\d{1,2})"\s*,\s*"params"\s*:\s*\["([^"]+)"\]/)
      if (!mm) continue
      const v = parseFloat(mm[2])
      if (!Number.isNaN(v)) map[mm[1]] = v
    }
    return map
  }, [])

  const parseBoxTemps = useCallback((msgs: MsgEvent[]): Record<string, number> => {
    const map: Record<string, number> = {}
    for (const m of msgs) {
      if (m.injected) continue
      const p = m.payload
      if (!p) continue
      const mm = p.match(/"UsC(\d{1,2})"\s*:\s*([0-9.]+)/)
      if (!mm) continue
      const v = parseFloat(mm[2])
      if (!Number.isNaN(v)) map[mm[1]] = v
    }
    return map
  }, [])

  useEffect(() => {
    if (theme === 'jour') {
      document.documentElement.dataset.theme = 'jour'
    } else {
      delete document.documentElement.dataset.theme
    }
    localStorage.setItem('aldes-theme', theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem('aldes-view', view)
  }, [view])

  useEffect(() => {
    if (histOpen) setHistOpen(false)
  }, [view])

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setInterval> | null = null
    const poll = async () => {
      try {
        const cfg = await getConfig()
        if (!alive) return
        setConfig({
          mode: cfg.mode,
          connected: cfg.connected ?? false,
          client_id: cfg.client_id ?? null,
          topics: cfg.topics ?? [],
          last_error: cfg.last_error ?? null,
          box_since: cfg.box_since ?? null,
          cloud_since: cfg.cloud_since ?? null
        })
      } catch {
        /* on réessaiera au prochain tick */
      }
    }
    poll()
    timer = setInterval(poll, 4000)
    return () => {
      alive = false
      if (timer) clearInterval(timer)
    }
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

  const reqFromSse = useMemo(() => parseRequested(messages), [messages, parseRequested])
  const boxTemps = useMemo(() => parseBoxTemps(messages), [messages, parseBoxTemps])

  useEffect(() => {
    setRequested((r) => ({ ...r, ...reqFromSse }))
  }, [reqFromSse])

  useEffect(() => {
    if (Object.keys(boxTemps).length === 0) return
    setConfirmed((c) => {
      const next = { ...c }
      for (const [zone, val] of Object.entries(boxTemps)) {
        const req = reqFromSse[zone]
        if (req !== undefined && Math.abs(req - val) < 0.01) {
          next[zone] = true
        }
      }
      return next
    })
  }, [boxTemps, reqFromSse])

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
          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={view === t.id}
                className={'tab' + (view === t.id ? ' active' : '')}
                onClick={() => setView(t.id)}
                title={t.title}
              >
                {t.label}
              </button>
            ))}
          </div>
          {view === 'log' && (
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
          )}
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
        {view === 'temps' && (
          <div className="streamCol">
            <TempsPanel
              clientId={config?.client_id ?? null}
              connected={config?.connected ?? false}
              requested={requested}
              confirmed={confirmed}
              onRequest={(zoneId, value) => {
                setRequested((r) => ({ ...r, [zoneId]: value }))
                setConfirmed((c) => ({ ...c, [zoneId]: false }))
              }}
            />
          </div>
        )}
        {view === 'commande' && (
          <div className="cmdCol">
            <CommandBuilder
              mode={config?.mode ?? null}
              connected={config?.connected ?? false}
              clientId={config?.client_id ?? null}
              defaultTopic={config?.mode === 'raw' ? config?.raw?.cmd_topic ?? null : null}
            />
            {config?.mode === 'raw' && <RawPanel />}
          </div>
        )}
        {view === 'log' && (
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
        )}
        {view === 'wrapper' && (
          <div className="streamCol">
            <WrapperPanel clientId={config?.client_id ?? null} />
          </div>
        )}
      </div>
    </div>
  )
}