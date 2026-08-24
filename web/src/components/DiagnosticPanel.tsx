import { useState, useCallback } from 'react'
import { getDiagnostic } from '../api'
import type { DiagnosticResult, DiagnosticCheck } from '../types'
import './DiagnosticPanel.css'

function CheckIcon({ check }: { check: DiagnosticCheck }) {
  if (check.ok) return <span className="diag-icon ok">&#10003;</span>
  if (check.warn) return <span className="diag-icon warn">!</span>
  return <span className="diag-icon fail">&#10007;</span>
}

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={'status-dot' + (ok ? ' on' : ' off')} />
}

export default function DiagnosticPanel() {
  const [result, setResult] = useState<DiagnosticResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const r = await getDiagnostic()
      setResult(r)
    } catch (e: any) {
      setError(e.message || 'Erreur inconnue')
    } finally {
      setLoading(false)
    }
  }, [])

  const find = (id: string) => result?.checks.find((c) => c.id === id)

  const box = find('box_connected')
  const cloud = find('cloud_connected')
  const mode = find('mode')

  return (
    <div className="diag-panel">
      <div className="diag-header">
        <h3>Diagnostic systeme</h3>
        <button onClick={run} disabled={loading} className="diag-run">
          {loading ? '...' : result ? '&#8635; Relancer' : '&#9654; Lancer le diagnostic'}
        </button>
      </div>

      {error && <div className="diag-error">{error}</div>}

      {result && (
        <>
          {/* Resume rapide : les 3 indicateurs cles */}
          <div className="diag-hero">
            <div className={'diag-hero-item' + (box?.ok ? ' ok' : ' ko')}>
              <StatusDot ok={!!box?.ok} />
              <span className="diag-hero-label">Box Aldes</span>
              <span className="diag-hero-val">{box?.detail ?? '—'}</span>
            </div>
            <div className={'diag-hero-item' + (cloud?.ok ? ' ok' : ' ko')}>
              <StatusDot ok={!!cloud?.ok} />
              <span className="diag-hero-label">Azure Cloud</span>
              <span className="diag-hero-val">{cloud?.detail ?? '—'}</span>
            </div>
            <div className={'diag-hero-item mode'}>
              <span className="diag-hero-label">Mode</span>
              <span className="diag-hero-val mode-val">{mode?.detail ?? '—'}</span>
            </div>
          </div>

          <div className={'diag-summary' + (result.ok ? ' ok' : ' ko')}>
            {result.passed}/{result.total} tests passes
          </div>

          <div className="diag-checks">
            {result.checks.map((c) => (
              <div key={c.id} className={'diag-check' + (c.ok ? ' ok' : c.warn ? ' warn' : ' ko')}>
                <CheckIcon check={c} />
                <div className="diag-check-body">
                  <div className="diag-label">{c.label}</div>
                  <div className="diag-detail">{c.detail}</div>
                  {c.rules && c.rules.length > 0 && (
                    <pre className="diag-rules">{c.rules.join('\n')}</pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {!result && !loading && (
        <div className="diag-empty">
          Cliquez sur "Lancer le diagnostic" pour verifier l'etat de tous les composants.
        </div>
      )}
    </div>
  )
}
