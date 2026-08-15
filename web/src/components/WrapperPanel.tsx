import { useMemo, useState } from 'react'
import { apiCall, type ApiResult } from '../api'
import styles from './WrapperPanel.module.css'

interface Props {
  clientId: string | null
}

interface RouteDef {
  id: string
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  path: string
  desc: string
  hasBody?: boolean
  bodyExample?: string
  queryParams?: { key: string; label: string; def?: string }[]
  placeholders?: { key: string; label: string; def?: string }[]
}

const ROUTES: RouteDef[] = [
  { id: 'config', method: 'GET', path: '/api/config', desc: 'État actuel du bridge (mode, connexion, client, raw).' },
  { id: 'state', method: 'GET', path: '/api/state', desc: 'Snapshot : config + trames de la session en cours.' },
  {
    id: 'logs',
    method: 'GET',
    path: '/api/logs',
    desc: 'Lecture à posteriori du log disque persistant (plus récent d’abord).',
    queryParams: [
      { key: 'limit', label: 'limit', def: '200' },
      { key: 'offset', label: 'offset', def: '0' }
    ]
  },
  {
    id: 'mode',
    method: 'POST',
    path: '/api/mode',
    desc: 'Changer de mode : proxy / bridge / raw.',
    hasBody: true,
    bodyExample: '{"mode":"proxy"}'
  },
  { id: 'raw', method: 'GET', path: '/api/raw', desc: 'Configuration du client MQTT natif (raw).' },
  {
    id: 'rawSet',
    method: 'POST',
    path: '/api/raw',
    desc: 'Enregistrer la config raw et forcer la reconnexion.',
    hasBody: true,
    bodyExample: '{"host":"","port":1883,"tls":true,"client_id":"","cmd_topic":"","evt_topic":""}'
  },
  {
    id: 'send',
    method: 'POST',
    path: '/api/send',
    desc: 'Injecter une trame MQTT vers la box (topic, payload JSON-RPC, qos).',
    hasBody: true,
    bodyExample:
      '{"topic":"devices/<clientId>/messages/devicebound","payload":"{\\"id\\":1,\\"jsonrpc\\":\\"2.0\\",\\"method\\":\\"changeMode\\",\\"params\\":[\\"V\\"]}","qos":1}'
  },
  { id: 'disconnect', method: 'POST', path: '/api/disconnect', desc: 'Déconnecter la box connectée.' },
  { id: 'clear', method: 'POST', path: '/api/clear', desc: 'Vider l’historique en mémoire du bridge.' },
  {
    id: 'token',
    method: 'POST',
    path: '/oauth2/token',
    desc: 'Rejeu : émission d’un token (inscrit un événement « authentification » dans le flux).',
    hasBody: true,
    bodyExample: '{"username":"demo","password":"demo"}'
  },
  {
    id: 'products',
    method: 'GET',
    path: '/aldesoc/v5/users/me/products',
    desc: 'Rejeu : produits Aldes + télémetrie capturée de la box (consommé par l’intégration HA).'
  },
  {
    id: 'updateThermo',
    method: 'PATCH',
    path: '/aldesoc/v5/users/me/products/{modem}/updateThermostats',
    desc: 'Rejeu : consigne thermostat (écriture loggée, non renvoyée à la box).',
    placeholders: [{ key: 'modem', label: 'modem', def: 'ABCDEF123456' }],
    hasBody: true,
    bodyExample: '{"TemperatureSet":21}'
  },
  {
    id: 'commands',
    method: 'POST',
    path: '/aldesoc/v5/users/me/products/{modem}/commands',
    desc: 'Rejeu : commande (écriture loggée, non renvoyée à la box).',
    placeholders: [{ key: 'modem', label: 'modem', def: 'ABCDEF123456' }],
    hasBody: true,
    bodyExample: '{"method":"changeMode","params":["V"]}'
  }
]

function fmtResult(r: ApiResult): string {
  try {
    return JSON.stringify(r.data, null, 2)
  } catch {
    return String(r.data)
  }
}

export default function WrapperPanel({ clientId }: Props) {
  const [open, setOpen] = useState<string | null>(null)
  const [body, setBody] = useState<Record<string, string>>({})
  const [query, setQuery] = useState<Record<string, Record<string, string>>>({})
  const [place, setPlace] = useState<Record<string, Record<string, string>>>({})
  const [results, setResults] = useState<Record<string, ApiResult | { error: string }>>({})
  const [busy, setBusy] = useState<Record<string, boolean>>({})

  const modemDefault = useMemo(
    () => (clientId ? clientId.split('-')[0] : 'ABCDEF123456'),
    [clientId]
  )

  const toggle = (id: string) => setOpen((o) => (o === id ? null : id))

  const run = async (route: RouteDef) => {
    setBusy((b) => ({ ...b, [route.id]: true }))
    setResults((r) => {
      const next = { ...r }
      delete next[route.id]
      return next
    })
    let path = route.path
    for (const p of route.placeholders ?? []) {
      const v = (place[route.id] ?? {})[p.key]?.trim() || p.def || (p.key === 'modem' ? modemDefault : '')
      path = path.split(`{${p.key}}`).join(encodeURIComponent(v))
    }
    const qs = (route.queryParams ?? [])
      .map((q) => {
        const v = (query[route.id] ?? {})[q.key]?.trim()
        return v === undefined || v === '' ? `${q.key}=${q.def ?? ''}` : `${q.key}=${encodeURIComponent(v)}`
      })
      .join('&')
    if (qs) path += '?' + qs

    let parsed: unknown
    if (route.hasBody) {
      const raw = (body[route.id] ?? route.bodyExample ?? '').split('<clientId>').join(clientId ?? '')
      try {
        parsed = JSON.parse(raw)
      } catch {
        setResults((r) => ({ ...r, [route.id]: { error: 'JSON de corps invalide' } }))
        setBusy((b) => ({ ...b, [route.id]: false }))
        return
      }
    }

    try {
      const res = await apiCall({
        method: route.method,
        path,
        body: route.hasBody ? parsed : undefined,
        contentType: route.id === 'token' ? 'form' : 'json'
      })
      setResults((r) => ({ ...r, [route.id]: res }))
    } catch (e) {
      setResults((r) => ({ ...r, [route.id]: { error: (e as Error).message } }))
    } finally {
      setBusy((b) => ({ ...b, [route.id]: false }))
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <span className={styles.title}>Appels API du wrapper</span>
        <span className={styles.sub}>
          routes exposées par le bridge — cliquez une route pour tester l’appel
          (même origine, pas d’authentification). Écritures = loggées, non relayées à la box.
        </span>
      </div>

      {ROUTES.map((r) => {
        const isOpen = open === r.id
        const res = results[r.id]
        return (
          <div key={r.id} className={styles.route + (isOpen ? ' ' + styles.open : '')}>
            <button className={styles.summary} onClick={() => toggle(r.id)}>
              <span className={styles.method + ' ' + styles[r.method.toLowerCase()]}>{r.method}</span>
              <code className={styles.path}>{r.path}</code>
              <span className={styles.chevron}>{isOpen ? '▾' : '▸'}</span>
            </button>
            {isOpen && (
              <div className={styles.detail}>
                <p className={styles.desc}>{r.desc}</p>

                {(r.placeholders ?? []).map((p) => (
                  <div key={p.key} className={styles.field}>
                    <label>{p.label} :</label>
                    <input
                      value={(place[r.id] ?? {})[p.key] ?? ''}
                      onChange={(e) =>
                        setPlace((m) => ({
                          ...m,
                          [r.id]: { ...(m[r.id] ?? {}), [p.key]: e.target.value }
                        }))
                      }
                      placeholder={p.key === 'modem' ? modemDefault : p.def}
                      spellCheck={false}
                    />
                  </div>
                ))}

                {(r.queryParams ?? []).map((q) => (
                  <div key={q.key} className={styles.field}>
                    <label>{q.key} :</label>
                    <input
                      value={(query[r.id] ?? {})[q.key] ?? ''}
                      onChange={(e) =>
                        setQuery((m) => ({
                          ...m,
                          [r.id]: { ...(m[r.id] ?? {}), [q.key]: e.target.value }
                        }))
                      }
                      placeholder={q.def ?? ''}
                      spellCheck={false}
                    />
                  </div>
                ))}

                {r.hasBody && (
                  <div className={styles.field}>
                    <label>corps {r.id === 'token' ? '(form)' : '(JSON)'} :</label>
                    <textarea
                      rows={5}
                      value={body[r.id] ?? r.bodyExample ?? ''}
                      onChange={(e) => setBody((m) => ({ ...m, [r.id]: e.target.value }))}
                      spellCheck={false}
                    />
                  </div>
                )}

                <div className={styles.actions}>
                  <button onClick={() => run(r)} disabled={!!busy[r.id]}>
                    {busy[r.id] ? '…' : 'exécuter'}
                  </button>
                </div>

                {res && (
                  <div className={styles.result}>
                    {'error' in res ? (
                      <div className={styles.err}>erreur : {res.error}</div>
                    ) : (
                      <>
                        <div className={styles.meta}>
                          <span className={res.ok ? styles.codeOk : styles.codeErr}>
                            {res.status} {res.statusText}
                          </span>
                          <span>{res.ms} ms</span>
                        </div>
                        <pre className={styles.pre}>{fmtResult(res)}</pre>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}