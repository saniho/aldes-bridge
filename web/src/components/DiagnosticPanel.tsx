import { useState, useCallback } from 'react'
import { getDiagnostic } from '../api'
import type { DiagnosticResult, DiagnosticCheck } from '../types'
import './DiagnosticPanel.css'

function CheckIcon({ check }: { check: DiagnosticCheck }) {
  if (check.ok) return <span className="diag-icon ok">&#10003;</span>
  if (check.warn) return <span className="diag-icon warn">!</span>
  return <span className="diag-icon fail">&#10007;</span>
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
