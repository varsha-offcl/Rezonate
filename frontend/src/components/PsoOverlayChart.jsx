import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
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

// GA plan = neutral ink (the original, un-corrected reference), same
// convention as SocChart's floor policy. PSO-corrected = emerald, the same
// "this is the better one" accent used for the TFT and the MILP oracle
// elsewhere in the dashboard.
const GA_COLOR = { light: '#101820', dark: '#e7eef0' }
const PSO_COLOR = { light: '#1e9e73', dark: '#33c990' }
// The concept artifact fills its trust-region band with the same soft accent
// green as the forecast's P10-P90 band -- one "uncertainty/tolerance region"
// visual language reused everywhere, not a one-off color.
const TRUST_FILL = { light: '#1e9e73', dark: '#33c990' }

function formatHour(ts) {
  return `${new Date(ts).getHours()}:00`
}

export default function PsoOverlayChart() {
  const { data, loading, error } = useData('pso_corrections.json')
  const isDark = useIsDark()

  const chartData = useMemo(() => {
    if (!data) return []
    return data.timestamps.map((ts, i) => ({
      timestamp: ts,
      ga_plan_kw: data.ga_plan_kw[i],
      corrected_kw: data.corrected_kw[i],
      trust_band: [data.trust_low_kw[i], data.trust_high_kw[i]],
    }))
  }, [data])

  const windowStart = data ? data.timestamps[data.correction_hour] : null
  const windowEnd = data ? data.timestamps[Math.min(data.correction_hour + data.window_hours, data.timestamps.length - 1)] : null

  return (
    <Card
      title="GA plan vs. PSO-corrected dispatch"
      subtitle={
        data
          ? `${data.day} — PSO corrects hours ${data.correction_hour}:00–${data.correction_hour + data.window_hours}:00 once actuals diverge from the forecast, bounded to the shaded trust region.`
          : undefined
      }
    >
      <LoadingError loading={loading} error={error} />
      {!loading && error && (
        <p className="text-sm text-muted">
          Available once PSO has run — run{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            python -m src.optimization.pso_refiner
          </code>{' '}
          then re-export.
        </p>
      )}
      {data && (
        <>
          <ResponsiveContainer width="100%" height={330}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
              <XAxis dataKey="timestamp" tickFormatter={formatHour} interval={2} tick={axisTick} />
              <YAxis
                tick={axisTick}
                width={60}
                label={{ value: 'kW', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }}
              />
              <Tooltip labelFormatter={formatHour} {...tooltipProps(isDark)} />
              <Legend wrapperStyle={legendStyle} />
              <ReferenceLine y={0} stroke={isDark ? '#69787e' : '#8a9aa0'} />
              {windowStart != null && (
                <ReferenceArea
                  x1={windowStart}
                  x2={windowEnd}
                  fill={isDark ? '#e3a94d' : '#b9791a'}
                  fillOpacity={0.08}
                  label={{ value: 'correction window', position: 'insideTop', fontSize: 10, fill: isDark ? '#e3a94d' : '#b9791a' }}
                />
              )}
              <Area
                type="monotone"
                dataKey="trust_band"
                name="±10% trust region"
                stroke="none"
                fill={isDark ? TRUST_FILL.dark : TRUST_FILL.light}
                fillOpacity={0.12}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="ga_plan_kw"
                name="GA plan"
                stroke={isDark ? GA_COLOR.dark : GA_COLOR.light}
                strokeWidth={2}
                strokeDasharray="5 3"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="corrected_kw"
                name="PSO-corrected"
                stroke={isDark ? PSO_COLOR.dark : PSO_COLOR.light}
                strokeWidth={2.25}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="mt-3 text-xs text-muted">
            Realized cost against what actually happened that day: GA plan alone EUR{' '}
            {data.ga_realized_cost.toFixed(2)} → GA+PSO (trust region) EUR {data.corrected_realized_cost.toFixed(2)}
            {data.unbounded_realized_cost != null && (
              <>
                {' '}— an unbounded PSO reaches EUR {data.unbounded_realized_cost.toFixed(2)} on this single event
                (expected: it's a strict relaxation of the same problem). What the trust region buys — schedule
                stability rather than PSO silently re-deriving GA's job — only shows up at full-season scale.
              </>
            )}
          </p>
        </>
      )}
    </Card>
  )
}
