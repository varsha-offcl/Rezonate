import { useMemo } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { axisTick, legendStyle, tooltipProps } from '../lib/chartTheme'
import { useIsDark } from '../lib/useIsDark'
import Card from './Card'
import LoadingError from './LoadingError'

const RULE_BASED_COLOR = { light: '#101820', dark: '#e7eef0' }
const ORACLE_COLOR = { light: '#1e9e73', dark: '#33c990' }
const BOUND_COLOR = { light: '#c0442f', dark: '#e2584f' }

function formatTick(ts) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:00`
}

export default function SocChart({ seasonData, weekIndex }) {
  const isDark = useIsDark()

  const { chartData, loading, soc_min, soc_max } = useMemo(() => {
    if (!seasonData) return { chartData: [], loading: true, soc_min: 0.2, soc_max: 0.9 }
    const startHour = weekIndex * 7 * 24
    const endHour = Math.min(startHour + 7 * 24, seasonData.timestamps.length)
    const rows = []
    for (let i = startHour; i <= endHour && i < seasonData.timestamps.length; i++) {
      rows.push({
        timestamp: seasonData.timestamps[i],
        rule_based: +(seasonData.policies.rule_based.soc[i] * 100).toFixed(2),
        oracle: +(seasonData.policies.oracle.soc[i] * 100).toFixed(2),
      })
    }
    return { chartData: rows, loading: false, soc_min: seasonData.soc_min, soc_max: seasonData.soc_max }
  }, [seasonData, weekIndex])

  return (
    <Card
      title="Battery state of charge"
      subtitle={
        !loading
          ? `Bounded ${(soc_min * 100).toFixed(0)}%–${(soc_max * 100).toFixed(0)}% (dashed). The oracle returns to its starting SOC by design; the rule-based floor has no such foresight.`
          : undefined
      }
    >
      <LoadingError loading={loading} error={null} />
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
            <XAxis dataKey="timestamp" tickFormatter={formatTick} minTickGap={40} tick={axisTick} />
            <YAxis domain={[0, 100]} tick={axisTick} width={44} unit="%" />
            <Tooltip labelFormatter={formatTick} {...tooltipProps(isDark)} />
            <Legend wrapperStyle={legendStyle} />
            <ReferenceLine y={soc_min * 100} stroke={isDark ? BOUND_COLOR.dark : BOUND_COLOR.light} strokeDasharray="4 3" />
            <ReferenceLine y={soc_max * 100} stroke={isDark ? BOUND_COLOR.dark : BOUND_COLOR.light} strokeDasharray="4 3" />
            <Line
              type="monotone"
              dataKey="rule_based"
              name="Rule-based (floor)"
              stroke={isDark ? RULE_BASED_COLOR.dark : RULE_BASED_COLOR.light}
              strokeWidth={1.75}
              strokeDasharray="5 3"
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="oracle"
              name="MILP oracle (ceiling)"
              stroke={isDark ? ORACLE_COLOR.dark : ORACLE_COLOR.light}
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
