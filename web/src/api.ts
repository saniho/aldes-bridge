import type { Mode } from './types'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.error ?? body.detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export async function getConfig(): Promise<import('./types').Config> {
  return json<import('./types').Config>(await fetch('/api/config'))
}

export async function getRaw(): Promise<import('./types').RawConfig> {
  return json<import('./types').RawConfig>(await fetch('/api/raw'))
}

export async function setRaw(
  cfg: Partial<import('./types').RawConfig>
): Promise<import('./types').RawConfig> {
  return json<import('./types').RawConfig>(
    await fetch('/api/raw', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        host: cfg.host ?? '',
        port: cfg.port ?? 1883,
        tls: cfg.tls ?? true,
        client_id: cfg.client_id ?? '',
        cmd_topic: cfg.cmd_topic ?? '',
        evt_topic: cfg.evt_topic ?? ''
      })
    })
  )
}

export async function setMode(mode: Mode): Promise<{ mode: Mode }> {
  return json<{ mode: Mode }>(
    await fetch('/api/mode', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ mode })
    })
  )
}

export async function sendCommand(
  topic: string,
  payload: string,
  qos: number
): Promise<{ ok: boolean; topic?: string; qos?: number; bytes?: number; error?: string }> {
  return json<{ ok: boolean; topic?: string; qos?: number; bytes?: number; error?: string }>(
    await fetch('/api/send', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ topic, payload, qos })
    })
  )
}

export interface ConsigneEntry {
  requested: number
  confirmed: boolean
  ts?: string
}

export async function getConsignes(): Promise<Record<string, ConsigneEntry>> {
  return json<{ consignes: Record<string, ConsigneEntry> }>(await fetch('/api/consigne')).then(
    (r) => r.consignes
  )
}

export async function requestConsigne(
  zone: string,
  value: number
): Promise<Record<string, ConsigneEntry>> {
  return json<{ consignes: Record<string, ConsigneEntry> }>(
    await fetch('/api/consigne', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ zone, value })
    })
  ).then((r) => r.consignes)
}

export async function disconnect(): Promise<{ ok: boolean }> {
  return json<{ ok: boolean }>(await fetch('/api/disconnect', { method: 'POST' }))
}

export async function clearHistory(): Promise<{ ok: boolean }> {
  return json<{ ok: boolean }>(await fetch('/api/clear', { method: 'POST' }))
}

export interface LogPage {
  total: number
  limit: number
  offset: number
  events: import('./types').BridgeEvent[]
}

export async function getLogs(limit: number, offset: number): Promise<LogPage> {
  return json<LogPage>(await fetch(`/api/logs?limit=${limit}&offset=${offset}`))
}

export async function getHistoryKeys(): Promise<import('./types').HistoryKey[]> {
  return json<{ keys: import('./types').HistoryKey[] }>(await fetch('/api/history/keys')).then(
    (r) => r.keys
  )
}

export async function getHistorySeries(
  key: string,
  start?: number,
  end?: number,
  bucket?: number
): Promise<import('./types').HistoryPoint[]> {
  const qs = new URLSearchParams({ key })
  if (start !== undefined) qs.set('start', String(start))
  if (end !== undefined) qs.set('end', String(end))
  if (bucket !== undefined) qs.set('bucket', String(bucket))
  return json<{ samples: import('./types').HistoryPoint[] }>(
    await fetch(`/api/history/series?${qs}`)
  ).then((r) => r.samples)
}

export async function getHistoryTable(
  start?: number,
  end?: number,
  limit = 500,
  offset = 0
): Promise<import('./types').HistoryTablePage> {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (start !== undefined) qs.set('start', String(start))
  if (end !== undefined) qs.set('end', String(end))
  return json<import('./types').HistoryTablePage>(await fetch(`/api/history/table?${qs}`))
}

export async function getProducts(): Promise<import('./types').AldesProduct[]> {
  return json<import('./types').AldesProduct[]>(
    await fetch('/aldesoc/v5/users/me/products')
  )
}

export interface ApiCallOptions {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  body?: unknown
  contentType?: 'json' | 'form'
}

export interface ApiResult {
  ok: boolean
  status: number
  statusText: string
  ms: number
  data: unknown
}

export async function apiCall(opts: ApiCallOptions): Promise<ApiResult> {
  const started = performance.now()
  const headers: Record<string, string> = {}
  let body: BodyInit | undefined
  if (opts.body !== undefined) {
    if (opts.contentType === 'form') {
      headers['content-type'] = 'application/x-www-form-urlencoded'
      body = new URLSearchParams(
        opts.body as Record<string, string>
      ).toString()
    } else {
      headers['content-type'] = 'application/json'
      body = JSON.stringify(opts.body)
    }
  }
  const res = await fetch(opts.path, { method: opts.method, headers, body })
  const ms = Math.round(performance.now() - started)
  let data: unknown
  try {
    data = await res.json()
  } catch {
    data = await res.text()
  }
  return { ok: res.ok, status: res.status, statusText: res.statusText, ms, data }
}