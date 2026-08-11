export type Mode = 'proxy' | 'bridge' | 'raw'

export interface RawConfig {
  enabled: boolean
  host: string
  port: number
  tls: boolean
  client_id: string
  cmd_topic: string
  evt_topic: string
}

export interface Config {
  mode: Mode
  connected: boolean
  client_id: string | null
  topics: string[]
  last_error?: string | null
  raw?: RawConfig
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
  session?: number | string | null
  host?: string | null
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