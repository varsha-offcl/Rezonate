import { useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
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

const POLICIES = {
  oracle: { label: 'MILP oracle (ceiling)' },
  rule_based: { label: 'Rule-based (floor)' },
}

const LOAD_COLOR = { light: '#101820', dark: '#e7eef0' }
const COLORS = SERIES

function formatTick(ts) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:00`
}

export default function DispatchChart({ seasonData, weekIndex }) {
  const { data: oracleSummary } = useData('oracle.json')
  const [policy, setPolicy] = useState('oracle')
  const isDark = useIsDark()

  const { chartData, loading, error } = useMemo(() => {
    if (!seasonData) return { chartData: [], loading: true, error: null }
    const startHour = weekIndex * 7 * 24
    const endHour = Math.min(startHour + 7 * 24, seasonData.timestamps.length)
    const p = seasonData.policies[policy]
    const rows = []
    for (let i = startHour; i < endHour; i++) {
      rows.push({
        timestamp: seasonData.timestamps[i],
        solar_kw: seasonData.solar_kw[i],
        wind_kw: seasonData.wind_kw[i],
        load_kw: seasonData.load_kw[i],
        batteryDischarge: p.battery_kw[i] > 0 ? p.battery_kw[i] : 0,
        batteryCharge: p.battery_kw[i] < 0 ? p.battery_kw[i] : 0,
        gridImport: p.import_kw[i] > 0 ? p.import_kw[i] : 0,
        gridExport: p.export_kw[i] > 0 ? -p.export_kw[i] : 0,
      })
    }
    return { chartData: rows, loading: false, error: null }
  }, [seasonData, policy, weekIndex])

  const c = (key) => (isDark ? COLORS[key].dark : COLORS[key].light)

  return (
    <Card
      title="Dispatch: generation, load, battery, grid"
      subtitle="Above zero: what met load. Below zero: where surplus went — battery charge or grid export."
      right={
        seasonData && (
          <select
            value={policy}
            onChange={(e) => setPolicy(e.target.value)}
            className="rounded-lg border border-rail bg-surface px-2.5 py-1.5 text-sm text-ink transition-colors hover:border-accent focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
          >
            {Object.entries(POLICIES).map(([key, cfg]) => (
              <option key={key} value={key}>{cfg.label}</option>
            ))}
          </select>
        )
      }
    >
      <LoadingError loading={loading} error={error} />
      {chartData.length > 0 && (
        <>
          <ResponsiveContainer width="100%" height={380}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
              <XAxis dataKey="timestamp" tickFormatter={formatTick} minTickGap={40} tick={axisTick} />
              <YAxis
                tick={axisTick}
                width={60}
                label={{ value: 'kW', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }}
              />
              <Tooltip labelFormatter={formatTick} {...tooltipProps(isDark)} />
              <Legend wrapperStyle={legendStyle} />
              <ReferenceLine y={0} stroke={isDark ? '#69787e' : '#8a9aa0'} />
              <Area stackId="flow" type="monotone" dataKey="solar_kw" name="Solar" stroke="none" fill={c('solar')} fillOpacity={0.85} isAnimationActive={false} />
              <Area stackId="flow" type="monotone" dataKey="wind_kw" name="Wind" stroke="none" fill={c('wind')} fillOpacity={0.85} isAnimationActive={false} />
              <Area stackId="flow" type="monotone" dataKey="batteryDischarge" name="Battery" stroke="none" fill={c('battery')} fillOpacity={0.85} isAnimationActive={false} />
              <Area stackId="flow" type="monotone" dataKey="gridImport" name="Grid" stroke="none" fill={c('grid')} fillOpacity={0.85} isAnimationActive={false} />
              <Area stackId="flow" type="monotone" dataKey="batteryCharge" name="Battery charge" legendType="none" stroke="none" fill={c('battery')} fillOpacity={0.85} isAnimationActive={false} />
              <Area stackId="flow" type="monotone" dataKey="gridExport" name="Grid export" legendType="none" stroke="none" fill={c('grid')} fillOpacity={0.85} isAnimationActive={false} />
              <Line type="monotone" dataKey="load_kw" name="Load" stroke={isDark ? LOAD_COLOR.dark : LOAD_COLOR.light} strokeWidth={2.5} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
          {oracleSummary && (
            <p className="mt-3 text-xs text-muted">
              Full test season ({oracleSummary.season_hours.toLocaleString()}h): no battery (idle) costs EUR{' '}
              {oracleSummary.idle.total_cost.toLocaleString()}; rule-based floor EUR{' '}
              {oracleSummary.rule_based.total_cost.toLocaleString()}; MILP oracle ceiling EUR{' '}
              {oracleSummary.oracle.true_cost.toLocaleString()} — the rule-based floor captures{' '}
              {oracleSummary.rule_based_capture_pct}% of the achievable saving. GA/PSO aim to close the rest.
            </p>
          )}
        </>
      )}
    </Card>
  )
}
