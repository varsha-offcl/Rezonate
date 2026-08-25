import { useMemo } from 'react'
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
import { axisTick, legendStyle, tooltipProps } from '../lib/chartTheme'
import { useData } from '../lib/useData'
import { useIsDark } from '../lib/useIsDark'
import Card from './Card'
import LoadingError from './LoadingError'

// Same convention as SocChart: the reference series (population mean) is
// neutral ink, the meaningful series (best individual) gets the accent.
const BEST_COLOR = { light: '#1e9e73', dark: '#33c990' }
const MEAN_COLOR = { light: '#101820', dark: '#e7eef0' }

export default function ConvergenceChart() {
  const { data, loading, error } = useData('ga_convergence.json')
  const isDark = useIsDark()

  const chartData = useMemo(() => data?.rows ?? [], [data])

  return (
    <Card
      title="GA convergence"
      subtitle="Best and mean fitness (season cost, EUR — lower is better) per generation, population 100."
    >
      {loading && <LoadingError loading={loading} error={null} />}
      {!loading && error && (
        <p className="text-sm text-muted">
          Available once the GA has run — run{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            python -m src.optimization.ga_scheduler
          </code>{' '}
          then re-export, and this chart populates from its generation log.
        </p>
      )}
      {data && (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
            <XAxis dataKey="generation" tick={axisTick} label={{ value: 'generation', position: 'insideBottom', offset: -3, fontSize: 11, fill: 'var(--muted-2)' }} />
            <YAxis tick={axisTick} width={60} />
            <Tooltip {...tooltipProps(isDark)} />
            <Legend wrapperStyle={legendStyle} />
            <Line
              type="monotone"
              dataKey="mean"
              name="Mean fitness"
              stroke={isDark ? MEAN_COLOR.dark : MEAN_COLOR.light}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="best"
              name="Best fitness"
              stroke={isDark ? BEST_COLOR.dark : BEST_COLOR.light}
              strokeWidth={2.25}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}
