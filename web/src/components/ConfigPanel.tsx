import { useState, useEffect } from 'react'
import { getAppConfig, setAppConfig } from '../api'
import type { AppConfig } from '../types'
import './ConfigPanel.css'

function fmtBytes(n: number): string {
  if (n >= 1024 * 1024 * 1024) return (n / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(0) + ' MB'
  if (n >= 1024) return (n / 1024).toFixed(0) + ' KB'
  return n + ' B'
}

function parseBytes(s: string): number | null {
  const m = s.trim().match(/^(\d+(?:\.\d+)?)\s*(gb|mb|kb|go|mo|ko)?$/i)
  if (!m) return null
  const n = parseFloat(m[1])
  const u = (m[2] || '').toLowerCase()
  if (u === 'gb' || u === 'go') return Math.round(n * 1024 * 1024 * 1024)
  if (u === 'mb' || u === 'mo') return Math.round(n * 1024 * 1024)
  if (u === 'kb' || u === 'ko') return Math.round(n * 1024)
  return Math.round(n)
}

export default function ConfigPanel() {
  const [cfg, setCfg] = useState<AppConfig | null>(null)
  const [days, setDays] = useState('')
  const [logSize, setLogSize] = useState('')
  const [dryRun, setDryRun] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    getAppConfig().then((c) => {
      setCfg(c)
      setDays(String(c.history_retention_days))
      setLogSize(fmtBytes(c.log_retention_max_bytes))
      setDryRun(c.ha_mqtt_dry_run)
    })
  }, [])

  async function save() {
    setSaving(true)
    setMsg('')
    try {
      const updates: Partial<AppConfig> = {}
      const d = parseInt(days, 10)
      if (!isNaN(d)) updates.history_retention_days = d
      const bytes = parseBytes(logSize)
      if (bytes !== null && bytes > 0) updates.log_retention_max_bytes = bytes
      updates.ha_mqtt_dry_run = dryRun
      const c = await setAppConfig(updates)
      setCfg(c)
      setDays(String(c.history_retention_days))
      setLogSize(fmtBytes(c.log_retention_max_bytes))
      setDryRun(c.ha_mqtt_dry_run)
      setMsg('Sauvegarde')
      setTimeout(() => setMsg(''), 2000)
    } catch (e: any) {
      setMsg('Erreur: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!cfg) return <div className="config-loading">Chargement...</div>

  return (
    <div className="config-panel">
      <h3>Configuration</h3>
      <div className="config-grid">
        <label>
          Retention historique (jours)
          <input
            type="number"
            min={1}
            max={3650}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </label>
        <label>
          Taille max logs
          <input
            type="text"
            value={logSize}
            onChange={(e) => setLogSize(e.target.value)}
            placeholder="25 MB"
          />
        </label>
      </div>
      <div className="config-toggle-row">
        <label className="config-toggle">
          <input
            type="checkbox"
            checked={!dryRun}
            onChange={(e) => setDryRun(!e.target.checked)}
          />
          <span>Envoyer commandes HA vers la box</span>
        </label>
        <span className="config-toggle-hint">
          {dryRun ? 'Desactive — commandes logguees uniquement' : 'Active — commandes envoyees a la PAC'}
        </span>
      </div>
      <div className="config-actions">
        <button onClick={save} disabled={saving}>
          {saving ? '...' : 'Appliquer'}
        </button>
        {msg && <span className="config-msg">{msg}</span>}
      </div>
    </div>
  )
}
