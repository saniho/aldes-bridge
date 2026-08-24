export type Mode = 'proxy' | 'bridge' | 'listen' | 'raw'

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
  azure_ip?: string | null
  consignes?: Record<string, { requested: number; confirmed: boolean; ts?: string }>
  server_version?: string
  ui_version?: string
  history_days?: number | null
  profile?: DeviceProfile | null
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
  blocked?: boolean
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

export interface ConsigneEvent {
  kind: 'consigne'
  zone: string
  requested: number
  confirmed: boolean
  ts?: string
}

export type BridgeEvent = SnapshotEvent | MsgEvent | StatusEvent | ConsigneEvent

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

export interface HistoryKey {
  key: string
  kind: string
  samples: number
  last_ts: number | null
}

export interface HistoryPoint {
  ts: number
  value?: number
  min?: number
  max?: number
  avg?: number
  n?: number
}

export interface HistoryTablePage {
  total: number
  limit: number
  offset: number
  samples: Array<{ ts: number; kind: string; key: string; value: number }>
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

export interface DeviceMode {
  index: number
  code: string
  label: string
}

export interface DeviceCommand {
  id: string
  label: string
  method: string
  topic_pattern: string
  params: Array<{
    name: string
    type: string
    options_from?: string
    options?: Array<{ code: string; label: string }>
    pattern?: string
    min?: number
    max?: number
    step?: number
  }>
}

export interface DeviceUi {
  quick_modes?: Array<{ field: string; label: string }>
  show_thermostats?: boolean
  show_vacations?: boolean
  show_people?: boolean
  show_hot_water?: boolean
}

export interface DeviceProfile {
  id: string
  name: string
  description: string
  type: string
  air_modes: DeviceMode[]
  water_modes: DeviceMode[]
  commands: DeviceCommand[]
  ui: DeviceUi
}

export interface AppConfig {
  history_retention_days: number
  log_retention_max_bytes: number
}

export interface DiagnosticCheck {
  id: string
  label: string
  detail: string
  ok: boolean
  warn?: boolean
  ip?: string | null
  rules?: string[]
}

export interface DiagnosticResult {
  ok: boolean
  passed: number
  total: number
  checks: DiagnosticCheck[]
}