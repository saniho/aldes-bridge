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