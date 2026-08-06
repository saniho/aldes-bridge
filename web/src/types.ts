export type Mode = 'proxy' | 'bridge'

export interface Config {
  mode: Mode
  connected: boolean
  client_id: string | null
  topics: string[]
  last_error?: string | null
}

export interface MsgEvent {
  kind: 'message'
  ts: string
  direction: 'in' | 'out'
  type: string
  topic?: string | null
  payload?: string | null
  qos?: number
  injected?: boolean
  mode: Mode
}

export interface StatusEvent {
  kind: 'status'
  ts?: string
  connected?: boolean
  client_id?: string | null
  mode?: Mode
  prev_mode?: Mode
  subscribed_topics?: string[]
  last_error?: string | null
}

export interface SnapshotEvent {
  kind: 'snapshot'
  config: Config
  messages: MsgEvent[]
}

export type BridgeEvent = SnapshotEvent | MsgEvent | StatusEvent