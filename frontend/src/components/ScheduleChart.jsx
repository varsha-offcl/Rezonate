import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
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

// Same hue as DispatchChart's "Battery" — one entity, one color everywhere.
const BATTERY_COLOR = SERIES.battery

function formatHour(ts) {
  return `${new Date(ts).getHours()}:00`
}

export default function ScheduleChart() {
  const { data, loading, error } = useData('schedule.json')
  const isDark = useIsDark()

  const chartData = useMemo(() => {
    if (!data) return []
    return data.timestamps.map((ts, i) => ({ timestamp: ts, battery_kw: data.battery_kw[i] }))
  }, [data])

  return (
    <Card
      title="GA day-ahead schedule"
      subtitle="The GA's chosen 24-hour battery plan. Above zero: discharge. Below zero: charge."
    >
      {loading && <LoadingError loading={loading} error={null} />}
      {!loading && error && (
        <p className="text-sm text-muted">
          Available once the GA has run — run{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            python -m src.optimization.ga_scheduler
          </code>{' '}
          then re-export, and this chart populates from its chosen schedule.
        </p>
      )}
      {data && (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
            <XAxis dataKey="timestamp" tickFormatter={formatHour} interval={2} tick={axisTick} />
            <YAxis
              tick={axisTick}
              width={60}
              label={{ value: 'kW', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }}
            />
            <Tooltip labelFormatter={formatHour} {...tooltipProps(isDark)} />
            <ReferenceLine y={0} stroke={isDark ? '#69787e' : '#8a9aa0'} />
            <Bar
              dataKey="battery_kw"
              name="Battery"
              fill={isDark ? BATTERY_COLOR.dark : BATTERY_COLOR.light}
              radius={[2, 2, 2, 2]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}
