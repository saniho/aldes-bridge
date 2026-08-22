export const MODES: { code: string; label: string }[] = [
  { code: 'V', label: 'V · Quotidien' },
  { code: 'X', label: 'X · Boost' },
  { code: 'Y', label: 'Y · Invités' },
  { code: 'Z', label: 'Z · Programme' },
  { code: 'H', label: 'H · Hors-gel' },
  { code: 'E', label: 'E · Auto' },
  { code: 'A', label: 'A · Arrêt' },
  { code: 'B', label: 'B · Chaud (Heat)' },
  { code: 'F', label: 'F · Froid (Cool)' }
]

export const FNS: { id: string; label: string }[] = [
  { id: 'consigne', label: 'changeConsigneC<n> — consigne par zone (réel cloud)' },
  { id: 'ballon', label: 'changeMode — ballon eau chaude On/Off' },
  { id: 'air', label: 'changeMode — rafraîchissement air (confort/prog C/prog D/arrêt)' },
  { id: 'mode', label: 'changeMode — mode' },
  { id: 'vacances', label: 'changeMode — vacances (W)' },
  { id: 'cmo', label: 'changeCMO — override 0/1' },
  { id: 'custom', label: 'JSON libre (personnalisé)' }
]

export const ZONES: { id: string; label: string }[] = [
  { id: 'C0', label: 'C0 · Zone 1 (principale)' },
  { id: 'C1', label: 'C1 · Zone 2' },
  { id: 'C2', label: 'C2 · Zone 3' },
  { id: 'C3', label: 'C3 · Zone 4' },
  { id: 'C4', label: 'C4 · Zone 5' },
  { id: 'C5', label: 'C5 · Zone 6' },
  { id: 'C6', label: 'C6 · Zone 7' },
  { id: 'C7', label: 'C7 · Zone 8' },
  { id: 'C8', label: 'C8 · Zone 9' },
  { id: 'C9', label: 'C9 · Zone 10' }
]

export function topicFor(clientId: string): string {
  return `devices/${clientId}/messages/devicebound`
}

function randHex(n: number): string {
  let s = ''
  for (let i = 0; i < n; i++) s += Math.floor(Math.random() * 16).toString(16)
  return s
}

function randomUUID(): string {
  return (
    `${randHex(8)}-${randHex(4)}-4${randHex(3)}-` +
    `${(8 + Math.floor(Math.random() * 4)).toString(16)}${randHex(3)}-` +
    `${randHex(12)}`
  )
}

export function withPropBag(base: string, clientId: string | null): string {
  const m = base.match(/^devices\/([^/]+)\/messages\/devicebound$/)
  const id = m ? m[1] : clientId ?? ''
  const mid = randomUUID()
  const to = encodeURIComponent(`/devices/${id}/messages/deviceBound`)
  return `${base}/%24.mid=${mid}&%24.to=${to}&iothub-ack=full`
}

export function utcStamp(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}` +
    `${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`
  )
}

export function dateInputValue(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
