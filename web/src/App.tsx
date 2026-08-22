import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { useSse } from './hooks/useSse'
import { getConfig, setMode, disconnect, clearHistory, getLogs, getConsignes } from './api'
import type { BridgeEvent, Config, ConsigneEvent, Mode, MsgEvent } from './types'
import StatusBar from './components/StatusBar'
import MessageStream from './components/MessageStream'
import ModeDiagram from './components/ModeDiagram'
import StatsBar from './components/StatsBar'
import RawPanel from './components/RawPanel'
import CommandBuilder from './components/CommandBuilder'
import TempsPanel from './components/TempsPanel'
import WrapperPanel from './components/WrapperPanel'
import ProfileSelector from './components/ProfileSelector'
import './App.css'

const HistoryPanel = lazy(() => import('./components/HistoryPanel'))

type View = 'temps' | 'commande' | 'log' | 'wrapper' | 'historique'

function mergeConsignes(
  c: Record<string, { requested: number; confirmed: boolean; ts?: string }>
): Record<string, { requested: number; confirmed: boolean; ts?: string }> {
  const out: Record<string, { requested: number; confirmed: boolean; ts?: string }> = {}
  for (const [k, v] of Object.entries(c)) {
    out[k] = {
      requested: Number(v.requested),
      confirmed: Boolean(v.confirmed),
      ts: typeof v.ts === 'string' ? v.ts : undefined
    }
  }
  return out
}

const TABS: { id: View; label: string; title: string }[] = [
  { id: 'temps', label: '🌡 infos aldes', title: 'Températures / infos de la PAC' },
  { id: 'commande', label: '📤 commande', title: 'Envoyer des commandes à la box' }
]

const MORE: { id: View; label: string; title: string }[] = [
  { id: 'log', label: '📜 log', title: 'Trames MQTT en temps réel et historique' },
  { id: 'wrapper', label: '🔌 wrapper', title: 'Appels API du bridge (test interactif)' },
  { id: 'historique', label: '📊 historique', title: 'Historique des valeurs (télémétries & connexions)' }
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
    if (
      stored === 'temps' ||
      stored === 'commande' ||
      stored === 'log' ||
      stored === 'wrapper' ||
      stored === 'historique'
    ) {
      return stored
    }
    return 'log'
  })
  const [histOpen, setHistOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [consignes, setConsignes] = useState<
    Record<string, { requested: number; confirmed: boolean; ts?: string }>
  >({})
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
    localStorage.setItem('aldes-view', view)
  }, [view])

  useEffect(() => {
    if (histOpen) setHistOpen(false)
  }, [view])

  useEffect(() => {
    if (moreOpen) setMoreOpen(false)
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
          cloud_since: cfg.cloud_since ?? null,
          consignes: cfg.consignes ?? undefined,
          server_version: cfg.server_version ?? 'dev',
          ui_version: cfg.ui_version ?? 'dev',
          history_days: cfg.history_days ?? null,
          profile: cfg.profile ?? null
        })
        if (cfg.consignes) setConsignes(mergeConsignes(cfg.consignes))
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

  useEffect(() => {
    if (lastSnapshot?.consignes) setConsignes(mergeConsignes(lastSnapshot.consignes))
  }, [lastSnapshot])

  useEffect(() => {
    let alive = true
    getConsignes()
      .then((c) => {
        if (alive) setConsignes(mergeConsignes(c))
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    for (const e of events) {
      if (e.kind === 'consigne') {
        const ce = e as ConsigneEvent
        setConsignes((c) => ({ ...c, [ce.zone]: { requested: ce.requested, confirmed: ce.confirmed, ts: ce.ts } }))
      }
    }
  }, [events])

  const onMode = useCallback(async (m: Mode) => {
    const cur = config?.mode ?? m
    const msg =
      m === 'bridge'
        ? `Passer en mode bridge ?\n\nLa box ne passera plus par le cloud Azure (chemin : box → bridge uniquement).`
        : m === 'raw'
          ? `Passer en mode natif (broker) ?\n\nLe bridge se connectera en client MQTT au broker configuré (box <-> broker <-> bridge).`
          : m === 'listen'
            ? `Passer en mode listen ?\n\nLa télémétrie de la box remonte vers Azure, mais les commandes Azure → box seront bloquées (visibles dans le log, jamais transmises à la box).`
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
        <div className="topLeft">
          <div className="moreWrap">
            <button
              className={'burger' + (moreOpen ? ' active' : '') + (view === 'log' || view === 'wrapper' || view === 'historique' ? ' on' : '')}
              onClick={() => setMoreOpen((o) => !o)}
              title="Ouvrir les outils"
              aria-expanded={moreOpen}
              aria-haspopup="menu"
            >
              ☰
            </button>
            {moreOpen && (
              <div className="moreMenu" role="menu">
                {MORE.map((m) => (
                  <button
                    key={m.id}
                    role="menuitem"
                    className={'moreItem' + (view === m.id ? ' active' : '')}
                    onClick={() => setView(m.id)}
                    title={m.title}
                  >
                    {m.label}
                  </button>
                ))}
                <div className="moreSep" role="separator" />
                <button
                  role="menuitem"
                  className="moreItem"
                  onClick={() => setTheme((t) => (t === 'nuit' ? 'jour' : 'nuit'))}
                  title={theme === 'nuit' ? 'Passer en mode jour' : 'Passer en mode nuit'}
                >
                  {theme === 'nuit' ? '☀️ passer en mode jour' : '🌙 passer en mode nuit'}
                </button>
                <div className="moreSep" role="separator" />
                <button
                  role="menuitem"
                  className="moreItem danger"
                  onClick={onClear}
                  title="Vider le log persistant"
                >
                  🗑 vider le log
                </button>
                <div className="moreVersion" title="Versions du bridge">
                  UI v{config?.ui_version ?? 'dev'} · Backend v{config?.server_version ?? 'dev'}
                </div>
              </div>
            )}
          </div>
          <h1>Aldes Bridge</h1>
          <ProfileSelector
            currentProfile={config?.profile ?? null}
            onProfileChanged={(p) => setConfig((c) => c ? { ...c, profile: p } : c)}
          />
        </div>
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
              consignes={consignes}
              profile={config?.profile ?? null}
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
              theme={theme}
              profile={config?.profile ?? null}
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
        {view === 'historique' && (
          <div className="streamCol">
            <Suspense
              fallback={<div className="histLabel" style={{ padding: 12 }}>chargement…</div>}
            >
              <HistoryPanel historyDays={config?.history_days ?? null} />
            </Suspense>
          </div>
        )}
      </div>
    </div>
  )
}