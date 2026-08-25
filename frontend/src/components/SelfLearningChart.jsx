import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SERIES, axisTick, legendStyle, tooltipProps } from '../lib/chartTheme'
import { useData } from '../lib/useData'
import { useIsDark } from '../lib/useIsDark'
import Card from './Card'
import LoadingError from './LoadingError'

const WARM_COLOR = { light: '#1e9e73', dark: '#33c990' }
const COLD_COLOR = { light: '#101820', dark: '#e7eef0' }
const DIVERSITY_COLOR = SERIES.wind
const MUT_COLOR = { light: '#b9791a', dark: '#e3a94d' }

const VIEWS = [
  ['warmstart', 'Warm-starting'],
  ['adaptive', 'Self-adaptive mutation'],
]

export default function SelfLearningChart() {
  const { data, loading, error } = useData('learning.json')
  const [view, setView] = useState('warmstart')
  const isDark = useIsDark()

  const warmData = useMemo(() => {
    if (!data?.convergence) return []
    const { cold, warm } = data.convergence
    return cold.map((c, i) => ({ generation: i, cold: c, warm: warm[i] }))
  }, [data])

  const adaptiveData = useMemo(() => data?.adaptive_trace ?? [], [data])
  const c = (pair) => (isDark ? pair.dark : pair.light)

  const summary = data?.summary
  const subtitle =
    view === 'warmstart'
      ? 'Cost of the best schedule per GA generation. Cold starts from a random population; warm reuses the previous day’s elite schedules.'
      : 'As the population converges (diversity falls), the mutation rate self-adapts upward to keep exploring — no hand-tuning.'

  return (
    <Card
      title="Self-learning: solution reuse & self-tuning"
      subtitle={subtitle}
      right={
        data && (
          <div className="inline-flex rounded-lg border border-rail p-0.5">
            {VIEWS.map(([key, text]) => (
              <button
                key={key}
                onClick={() => setView(key)}
                className={
                  view === key
                    ? 'rounded-md bg-accent-soft px-3 py-1 text-sm font-medium text-accent-ink'
                    : 'rounded-md px-3 py-1 text-sm text-muted transition-colors hover:bg-surface-2'
                }
              >
                {text}
              </button>
            ))}
          </div>
        )
      }
    >
      {loading && <LoadingError loading={loading} error={null} />}
      {!loading && error && (
        <p className="text-sm text-muted">
          Available once the closed loop has run — run{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            python -m src.optimization.closed_loop
          </code>{' '}
          then re-export.
        </p>
      )}
      {data && view === 'warmstart' && (
        <>
          <ResponsiveContainer width="100%" height={330}>
            <LineChart data={warmData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
              <XAxis dataKey="generation" tick={axisTick} label={{ value: 'generation', position: 'insideBottom', offset: -3, fontSize: 11, fill: 'var(--muted-2)' }} />
              <YAxis tick={axisTick} width={70} label={{ value: 'best cost (EUR)', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }} />
              <Tooltip {...tooltipProps(isDark)} />
              <Legend wrapperStyle={legendStyle} />
              <Line type="monotone" dataKey="cold" name="Cold start (random)" stroke={c(COLD_COLOR)} strokeWidth={1.75} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="warm" name="Warm start (prev. day's elites)" stroke={c(WARM_COLOR)} strokeWidth={2.25} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          {summary && (
            <p className="mt-3 text-xs text-muted">
              Across {data.per_day.length} chained days, warm-starting reaches the cold run's fully-converged
              quality in {summary.mean_gen_warm} generations vs {summary.mean_gen_cold} — it begins already at
              that quality because consecutive days share a daily shape. The daily sub-problem is easy enough
              that even cold converges quickly, so the practical saving is modest; the mechanism would matter
              more on harder dispatch problems.
            </p>
          )}
        </>
      )}
      {data && view === 'adaptive' && (
        <ResponsiveContainer width="100%" height={330}>
          <LineChart data={adaptiveData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
            <XAxis dataKey="generation" tick={axisTick} label={{ value: 'generation', position: 'insideBottom', offset: -3, fontSize: 11, fill: 'var(--muted-2)' }} />
            <YAxis tick={axisTick} width={70} domain={[0, 1]} label={{ value: 'diversity / mutation rate', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }} />
            <Tooltip {...tooltipProps(isDark)} />
            <Legend wrapperStyle={legendStyle} />
            <Line type="monotone" dataKey="diversity" name="Population diversity" stroke={c(DIVERSITY_COLOR)} strokeWidth={2.25} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="mut_prob" name="Mutation rate (self-adapted)" stroke={c(MUT_COLOR)} strokeWidth={2.25} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}
