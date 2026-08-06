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

export async function getConfig(): Promise<{ mode: Mode }> {
  return json<{ mode: Mode }>(await fetch('/api/config'))
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
): Promise<{ ok: boolean; topic?: string; qos?: number; bytes?: number }> {
  return json<{ ok: boolean }>(
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