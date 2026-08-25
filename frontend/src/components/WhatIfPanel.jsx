import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import Card from './Card'

// The what-if feature talks to the FastAPI backend (src/api.py), which re-runs
// the real optimiser on each request. Unlike every other card (which reads
// static JSON), this one needs that server running.
const API_BASE = 'http://127.0.0.1:8000'

function costLabel(v) {
  // Cost < 0 means the microgrid earns money that day.
  return v < 0 ? `earns €${Math.abs(v).toFixed(2)}` : `costs €${v.toFixed(2)}`
}

export default function WhatIfPanel() {
  const [solarPct, setSolarPct] = useState(0)
  const [batteryKwh, setBatteryKwh] = useState(300)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [aiText, setAiText] = useState(null)
  const [aiSource, setAiSource] = useState('template') // 'template' | 'llm'
  const [aiLoading, setAiLoading] = useState(false)
  const [aiNote, setAiNote] = useState(null)

  async function rerun() {
    setLoading(true)
    setError(null)
    setAiText(null)       // drop any explanation from the previous run
    setAiSource('template')
    setAiNote(null)
    try {
      const res = await fetch(`${API_BASE}/whatif`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ solar_pct: solarPct, battery_kwh: batteryKwh }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setResult(await res.json())
    } catch {
      setError('Could not reach the optimiser server.')
    } finally {
      setLoading(false)
    }
  }

  async function rephrase() {
    if (!result) return
    setAiLoading(true)
    setAiNote(null)
    try {
      const res = await fetch(`${API_BASE}/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ facts: result.facts }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setAiText(json.explanation)
      setAiSource(json.source)
      if (json.source === 'template') {
        setAiNote('No GROQ_API_KEY set on the server — showing the deterministic version.')
      }
    } catch {
      setAiNote('Could not reach the explanation server — showing the deterministic version.')
    } finally {
      setAiLoading(false)
    }
  }

  const better = result && result.delta < 0
  const sameAsBaseline = result && Math.abs(result.delta) < 0.005

  return (
    <Card
      title="What-if: re-run the optimiser live"
      subtitle="Change an input and re-run the real GA against a representative summer day. Every result is a fresh optimisation, not a lookup."
    >
      <div className="flex flex-col gap-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="flex justify-between text-muted">
              <span>Solar output</span>
              <span className="font-mono tabular-nums">{solarPct > 0 ? '+' : ''}{solarPct}%</span>
            </span>
            <input type="range" min={-20} max={20} step={1} value={solarPct}
              onChange={(e) => setSolarPct(Number(e.target.value))}
              className="accent-accent" />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="flex justify-between text-muted">
              <span>Battery size</span>
              <span className="font-mono tabular-nums">{batteryKwh} kWh</span>
            </span>
            <input type="range" min={50} max={1000} step={50} value={batteryKwh}
              onChange={(e) => setBatteryKwh(Number(e.target.value))}
              className="accent-accent" />
          </label>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={rerun}
            disabled={loading}
            className="rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm font-medium text-accent-ink transition-opacity hover:opacity-90 disabled:cursor-progress disabled:opacity-55"
          >
            {loading ? 'Re-optimising…' : 'Re-run optimiser'}
          </button>
          {loading && <span className="text-sm text-muted">running a real GA (~2–3s)…</span>}
        </div>

        {error && (
          <div className="rounded-lg border border-live bg-live-soft p-3 text-sm text-live">
            {error} Start it with:{' '}
            <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
              .venv/Scripts/python -m uvicorn src.api:app --port 8000
            </code>
          </div>
        )}

        {result && !error && (
          <div className="rounded-xl border border-rail bg-surface-2 p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm text-muted">
                Representative day {result.day}
              </span>
              <span className="text-sm text-muted">
                baseline (300 kWh, normal solar): <span className="font-mono">{costLabel(result.baseline_cost)}</span>
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-display text-2xl font-semibold tracking-tight text-ink">
                Now {costLabel(result.new_cost)}
              </span>
              {sameAsBaseline ? (
                <span className="text-sm text-muted">— same as baseline</span>
              ) : (
                <span className={better
                  ? 'text-sm font-medium text-accent-ink'
                  : 'text-sm font-medium text-critical'}>
                  {better ? '▲ better by' : '▼ worse by'} €{Math.abs(result.delta).toFixed(2)} ({result.delta_pct > 0 ? '+' : ''}{result.delta_pct}%)
                </span>
              )}
            </div>

            {/* Explanation of the schedule the re-optimiser just produced. */}
            {result.explanation && (
              <div className="mt-4 border-t border-rail pt-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-2">
                    Why this plan
                  </span>
                  {aiSource === 'llm' && aiText && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-accent bg-accent-soft px-2.5 py-1 font-mono text-[11px] tracking-wide text-accent-ink">
                      <Sparkles className="h-3 w-3" /> AI-rephrased (Groq)
                    </span>
                  )}
                </div>
                <p className="text-sm leading-relaxed text-ink">{aiText ?? result.explanation}</p>
                <div className="mt-3 flex items-center gap-3">
                  <button
                    onClick={rephrase}
                    disabled={aiLoading}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-accent bg-accent-soft px-3 py-1.5 text-sm font-medium text-accent-ink transition-opacity hover:opacity-90 disabled:cursor-progress disabled:opacity-55"
                  >
                    <Sparkles className="h-4 w-4" />
                    {aiLoading ? 'Rephrasing…' : 'Rephrase with AI'}
                  </button>
                  <span className="text-xs text-muted-2">
                    A language model rewords the same computed facts — it invents no numbers.
                  </span>
                </div>
                {aiNote && <p className="mt-2 text-xs text-muted">{aiNote}</p>}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}
