import { useState, useRef, useEffect } from 'react'
import { MessageCircle, Send, X, ChevronDown, Zap, Battery, Sun, Wind, DollarSign, Gauge } from 'lucide-react'

const API_BASE = 'http://127.0.0.1:8000'

const FIELDS = [
  { key: 'solar_kw', label: 'Solar', unit: 'kW', icon: Sun, placeholder: 'e.g. 520', color: 'text-amber-500' },
  { key: 'wind_kw', label: 'Wind', unit: 'kW', icon: Wind, placeholder: 'e.g. 310', color: 'text-sky-500' },
  { key: 'load_kw', label: 'Demand', unit: 'kW', icon: Gauge, placeholder: 'e.g. 760', color: 'text-rose-500' },
  { key: 'price_per_kwh', label: 'Price', unit: '$/kWh', icon: DollarSign, placeholder: 'e.g. 0.18', color: 'text-green-500' },
  { key: 'battery_kwh', label: 'Battery', unit: 'kWh', icon: Battery, placeholder: 'e.g. 300', color: 'text-violet-500' },
  { key: 'soc_pct', label: 'Charge', unit: '%', icon: Zap, placeholder: 'e.g. 55', color: 'text-teal-500' },
]

const PRESETS = [
  { name: 'Sunny Day', solar_kw: 520, wind_kw: 50, load_kw: 400, price_per_kwh: 0.18, battery_kwh: 300, soc_pct: 55 },
  { name: 'Windy Night', solar_kw: 0, wind_kw: 310, load_kw: 200, price_per_kwh: 0.12, battery_kwh: 300, soc_pct: 40 },
  { name: 'High Demand', solar_kw: 450, wind_kw: 250, load_kw: 760, price_per_kwh: 0.25, battery_kwh: 500, soc_pct: 80 },
]

const SUGGESTIONS = [
  'Why did the battery charge at that time?',
  'How much money does the battery save?',
  'What is the battery efficiency?',
  'How much solar energy is generated daily?',
]

function ResultCard({ data }) {
  if (!data) return null
  const { result, schedule, totals } = data

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-rail bg-surface-2 p-4 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-ink">Daily cost</span>
        <span className="font-mono font-bold text-ink">€{result.new_cost.toFixed(2)}</span>
      </div>

      {result.delta !== 0 && (
        <div className="flex items-center justify-between text-[13px]">
          <span className="text-muted">vs. no battery (€{result.baseline_cost.toFixed(2)})</span>
          <span className={`font-mono font-semibold ${result.delta < 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
            {result.delta < 0 ? 'saves' : 'costs'} €{Math.abs(result.delta).toFixed(2)} ({result.delta_pct > 0 ? '+' : ''}{result.delta_pct}%)
          </span>
        </div>
      )}

      <div className="flex flex-wrap gap-2 text-[11px]">
        <span className="rounded bg-surface px-2 py-0.5 font-mono text-muted">import €{result.import_cost}</span>
        <span className="rounded bg-surface px-2 py-0.5 font-mono text-muted">export €{result.export_revenue}</span>
        <span className="rounded bg-surface px-2 py-0.5 font-mono text-muted">degrad €{result.degradation_cost}</span>
      </div>

      {totals && (
        <div className="border-t border-rail pt-2 text-[12px] text-muted">
          Charged {totals.charge_kwh} kWh | Discharged {totals.discharge_kwh} kWh |
          {totals.cycles > 1.1 ? ` ~${totals.cycles} cycles` : ' 1 cycle'} |
          Usable {totals.usable_capacity_kwh} kWh
        </div>
      )}

      {schedule && schedule.length > 0 && (
        <details className="border-t border-rail pt-2">
          <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-2 hover:text-muted">
            Battery schedule ({schedule.length} windows)
          </summary>
          <div className="mt-1.5 flex flex-col gap-1">
            {schedule.map((w, i) => (
              <div key={i} className="flex items-center justify-between text-[12px]">
                <span className={`font-medium ${w.action === 'charge' ? 'text-green-600 dark:text-green-400' : 'text-orange-600 dark:text-orange-400'}`}>
                  {w.action === 'charge' ? 'Charge' : 'Discharge'} {w.start}-{w.end}
                </span>
                <span className="font-mono text-muted">{w.avg_power_kw} kW x {w.hours}h = {w.energy_kwh} kWh</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

function ChatMessage({ role, text }) {
  return (
    <div className={`flex ${role === 'user' ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-[13px] leading-relaxed ${
        role === 'user'
          ? 'bg-accent-soft text-ink'
          : 'border border-rail bg-surface-2 text-ink'
      }`}>
        <p className="whitespace-pre-wrap">{text}</p>
      </div>
    </div>
  )
}

export default function ChatBox() {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const scrollRef = useRef(null)
  const chatInputRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [result, error, chatMessages, chatLoading])

  function handleChange(key, raw) {
    setValues(prev => {
      const next = { ...prev }
      if (raw === '') {
        delete next[key]
      } else {
        next[key] = raw
      }
      return next
    })
  }

  function applyPreset(preset) {
    const next = {}
    for (const f of FIELDS) {
      if (preset[f.key] != null) next[f.key] = String(preset[f.key])
    }
    setValues(next)
  }

  async function run() {
    if (loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    setChatMessages([])

    const body = {}
    for (const f of FIELDS) {
      const raw = values[f.key]
      if (raw != null && raw !== '') {
        const n = parseFloat(raw)
        if (!isNaN(n)) body[f.key] = n
      }
    }

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errText = await res.text()
        throw new Error(`Server error ${res.status}: ${errText}`)
      }
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError(e.message || 'Could not reach backend on port 8000')
    } finally {
      setLoading(false)
    }
  }

  async function sendChat(text) {
    const msg = text || chatInput.trim()
    if (!msg || chatLoading) return
    setChatInput('')

    setChatMessages(prev => [...prev, { role: 'user', text: msg }])
    setChatLoading(true)

    try {
      const res = await fetch(`${API_BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: msg,
          context: result || {},
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setChatMessages(prev => [...prev, { role: 'assistant', text: data.reply }])
    } catch {
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        text: 'Could not reach the server. Make sure the backend is running on port 8000.',
      }])
    } finally {
      setChatLoading(false)
    }
  }

  function handleChatKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendChat()
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Open optimizer"
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-white shadow-lg transition-transform hover:scale-105 active:scale-95"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[650px] w-[400px] flex-col overflow-hidden rounded-2xl border border-rail bg-surface shadow-lg sm:w-[440px]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-rail bg-surface-2 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-accent-ink">
            <Zap className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">Energy Optimizer</h3>
            <p className="text-[11px] text-muted">Enter values, optimize, then ask questions</p>
          </div>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setOpen(false)}
            aria-label="Minimise"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-ink"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
          <button
            onClick={() => { setOpen(false); setValues({}); setResult(null); setError(null); setChatMessages([]) }}
            aria-label="Close"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Scrollable body */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
        {/* Presets */}
        <div className="mb-4">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-2">Quick presets</p>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.name}
                onClick={() => applyPreset(p)}
                className="rounded-lg border border-rail bg-surface-2 px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:border-accent hover:bg-accent-soft"
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Input fields */}
        <div className="mb-4 flex flex-col gap-3">
          {FIELDS.map((f) => {
            const Icon = f.icon
            return (
              <div key={f.key} className="flex items-center gap-3">
                <Icon className={`h-5 w-5 flex-none ${f.color}`} />
                <label className="w-16 flex-none text-sm font-medium text-ink">{f.label}</label>
                <div className="relative flex-1">
                  <input
                    type="number"
                    step="any"
                    value={values[f.key] ?? ''}
                    onChange={(e) => handleChange(f.key, e.target.value)}
                    placeholder={f.placeholder}
                    className="w-full rounded-lg border border-rail bg-surface px-3 py-2 pr-16 text-sm text-ink placeholder:text-muted-2 focus:border-accent focus:outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                  />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-muted-2">
                    {f.unit}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Run button */}
        <button
          onClick={run}
          disabled={loading}
          className="mb-4 w-full rounded-xl bg-accent py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {loading ? 'Running optimizer...' : 'Optimize'}
        </button>

        {/* Error */}
        {error && (
          <div className="mb-4 rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Results */}
        <ResultCard data={result} />

        {/* Chat section — appears after optimization */}
        {result && (
          <div className="mt-4 border-t border-rail pt-4">
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-2">
              Ask a question about the results
            </p>

            {/* Suggestion chips — show when no chat yet */}
            {chatMessages.length === 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => sendChat(s)}
                    className="rounded-lg border border-rail bg-surface-2 px-2.5 py-1 text-[11px] text-ink transition-colors hover:border-accent hover:bg-accent-soft"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* Chat messages */}
            {chatMessages.length > 0 && (
              <div className="mb-3 flex flex-col gap-2">
                {chatMessages.map((msg, i) => (
                  <ChatMessage key={i} role={msg.role} text={msg.text} />
                ))}
                {chatLoading && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl border border-rail bg-surface-2 px-3 py-2 text-[13px] text-muted">
                      <span className="inline-flex gap-1">
                        <span className="animate-bounce" style={{ animationDelay: '0ms' }}>.</span>
                        <span className="animate-bounce" style={{ animationDelay: '150ms' }}>.</span>
                        <span className="animate-bounce" style={{ animationDelay: '300ms' }}>.</span>
                      </span>
                      {' '}Thinking...
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Chat input */}
            <div className="flex items-end gap-2">
              <input
                ref={chatInputRef}
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={handleChatKeyDown}
                placeholder="Ask anything about the results..."
                className="min-h-[36px] flex-1 rounded-xl border border-rail bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted-2 focus:border-accent focus:outline-none"
              />
              <button
                onClick={() => sendChat()}
                disabled={!chatInput.trim() || chatLoading}
                aria-label="Send"
                className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-accent text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
