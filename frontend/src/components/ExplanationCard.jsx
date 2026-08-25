import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { useData } from '../lib/useData'
import Card from './Card'
import LoadingError from './LoadingError'

// Like WhatIfPanel, the AI rephrasing talks to the FastAPI backend (src/api.py).
// The card always shows the deterministic template first (from static
// explanation.json), so it works with no backend and no internet; the button
// only *upgrades* the wording via a language model when the server is reachable.
const API_BASE = 'http://127.0.0.1:8000'

function Badge({ children, accent }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 font-mono text-[11px] tracking-wide ${
      accent ? 'border-accent bg-accent-soft text-accent-ink' : 'border-rail text-muted'
    }`}>
      {children}
    </span>
  )
}

export default function ExplanationCard() {
  const { data, loading, error } = useData('explanation.json')
  const [aiText, setAiText] = useState(null)
  const [source, setSource] = useState('template') // 'template' | 'llm'
  const [aiLoading, setAiLoading] = useState(false)
  const [aiNote, setAiNote] = useState(null)

  async function rephrase() {
    if (!data) return
    setAiLoading(true)
    setAiNote(null)
    try {
      const res = await fetch(`${API_BASE}/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ facts: data.facts }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setAiText(json.explanation)
      setSource(json.source)
      if (json.source === 'template') {
        setAiNote('No GROQ_API_KEY set on the server — showing the deterministic version.')
      }
    } catch {
      setAiNote('Could not reach the explanation server — showing the deterministic version.')
    } finally {
      setAiLoading(false)
    }
  }

  const text = aiText ?? data?.template_text
  const showingAi = source === 'llm' && aiText

  return (
    <Card
      title="Why this decision"
      subtitle={data ? `Plain-language explanation of the optimiser's battery moves on ${data.date}, generated from the actual forecast, price, and schedule.` : undefined}
      right={
        showingAi
          ? <Badge accent><Sparkles className="h-3 w-3" /> AI-rephrased (Groq)</Badge>
          : <Badge>Deterministic</Badge>
      }
    >
      <LoadingError loading={loading} error={error} />

      {data && (
        <div className="flex flex-col gap-4">
          <p className="text-[15px] leading-relaxed text-ink">{text}</p>

          {/* The verifiable facts behind the sentence — proof the wording is grounded. */}
          <div className="flex flex-wrap gap-2">
            {data.facts.windows.map((w, i) => (
              <span key={i} className="rounded-lg border border-rail bg-surface-2 px-2.5 py-1 font-mono text-[11px] text-muted">
                {w.action === 'charge' ? '↓ charge' : '↑ discharge'} {w.start}–{w.end} · €{w.mean_price_eur_mwh}/MWh
              </span>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={rephrase}
              disabled={aiLoading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm font-medium text-accent-ink transition-opacity hover:opacity-90 disabled:cursor-progress disabled:opacity-55"
            >
              <Sparkles className="h-4 w-4" />
              {aiLoading ? 'Rephrasing…' : 'Rephrase with AI'}
            </button>
            <span className="text-xs text-muted-2">
              A language model rewords the same computed facts — it invents no numbers or reasons.
            </span>
          </div>

          {aiNote && <p className="text-xs text-muted">{aiNote}</p>}
        </div>
      )}
    </Card>
  )
}
