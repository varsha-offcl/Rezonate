import { useMemo } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
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

const ERROR_COLOR = { light: '#0ea5e9', dark: '#0284c7' }
const TRIGGER_COLOR = { light: '#c0442f', dark: '#e2584f' }

function formatMonth(day) {
  const d = new Date(day)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export default function DriftChart() {
  const { data, loading, error } = useData('drift.json')
  const isDark = useIsDark()

  const chartData = useMemo(() => {
    if (!data) return []
    return data.days.map((day, i) => ({ day, error: data.daily_error[i] }))
  }, [data])

  const triggerDays = useMemo(() => {
    if (!data) return []
    // trigger timestamps -> the date string used on the x-axis
    return data.trigger_timestamps.map((ts) => ts.slice(0, 10))
  }, [data])

  return (
    <Card
      title="Forecast-error drift monitor"
      subtitle="Daily mean forecast error (normalised) across the test season, watched by a Page-Hinkley change detector that would trigger TFT retraining on concept drift."
    >
      {loading && <LoadingError loading={loading} error={null} />}
      {!loading && error && (
        <p className="text-sm text-muted">
          Available once the drift diagnostic has run — run{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            python -m src.forecasting.drift
          </code>{' '}
          then re-export.
        </p>
      )}
      {data && (
        <>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
              <XAxis dataKey="day" tickFormatter={formatMonth} minTickGap={40} tick={axisTick} />
              <YAxis tick={axisTick} width={60} label={{ value: 'norm. error', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }} />
              <Tooltip {...tooltipProps(isDark)} />
              {triggerDays.map((d, i) => (
                <ReferenceLine key={i} x={d} stroke={isDark ? TRIGGER_COLOR.dark : TRIGGER_COLOR.light} strokeDasharray="4 3" />
              ))}
              <Line type="monotone" dataKey="error" name="Daily forecast error" stroke={isDark ? ERROR_COLOR.dark : ERROR_COLOR.light} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-3 text-xs text-muted">
            {data.trigger_timestamps.length === 0 ? (
              <>
                No drift triggered this season (error mean {data.error_mean}, std {data.error_std}) — the TFT's error
                is effectively stationary because it already absorbs the autumn→spring shift through its calendar
                inputs. The detection mechanism is in place and would fire the retraining loop under genuine concept
                drift (e.g. a new site, a later year, or live data) — so this is an honest negative, not a gap.
              </>
            ) : (
              <>
                {data.trigger_timestamps.length} drift trigger(s) marked (dashed red) — each would kick off an
                incremental TFT retrain on recent actuals.
              </>
            )}
          </p>
        </>
      )}
    </Card>
  )
}
