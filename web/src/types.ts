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
  box_since?: number | null
  cloud_since?: number | null
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

export interface AldesThermostat {
  ThermostatId: string
  thermostatId?: string
  Name: string
  CurrentTemperature: number | null
  CurrentHumidity?: number | null
  TemperatureSet: number | null
}

export interface AldesIndicator {
  qte_eau_chaude: number | null
  tmp_principal: number | null
  current_air_mode: string | null
  current_water_mode: string | null
  date_debut_vac: string | null
  date_fin_vac: string | null
  hors_gel: boolean
  settings?: { people?: number | null }
  thermostats: AldesThermostat[]
}

export interface AldesProduct {
  modem: string
  serial_number: string
  reference: string
  name: string
  type: string
  isConnected: boolean
  lastUpdatedDate: string
  lastUpdatedAt: string | null
  updatedAt?: string | null
  indicator: AldesIndicator
}