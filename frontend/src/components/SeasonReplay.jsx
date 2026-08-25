import { useEffect, useMemo, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SERIES, axisTick, tooltipProps } from '../lib/chartTheme'
import { useIsDark } from '../lib/useIsDark'
import Card from './Card'

const POLICIES = {
  oracle: { label: 'MILP oracle (ceiling)' },
  rule_based: { label: 'Rule-based (floor)' },
}

const BATTERY_COLOR = SERIES.battery
const SOC_COLOR = { light: '#1e9e73', dark: '#33c990' }

function formatHour(ts) {
  return `${new Date(ts).getHours()}:00`
}

function formatDay(ts) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function SeasonReplay({ seasonData, weekIndex }) {
  const [policy, setPolicy] = useState('oracle')
  const [dayOffset, setDayOffset] = useState(0)
  const [playing, setPlaying] = useState(false)
  const isDark = useIsDark()
  const timerRef = useRef(null)

  const days = seasonData?.days ?? 0
  const weekStartDay = weekIndex * 7
  const weekDays = Math.min(7, days - weekStartDay)

  useEffect(() => {
    setDayOffset(0)
    setPlaying(false)
  }, [weekIndex])

  useEffect(() => {
    if (!playing || !weekDays) return
    timerRef.current = setInterval(() => {
      setDayOffset((d) => (d + 1) % weekDays)
    }, 400)
    return () => clearInterval(timerRef.current)
  }, [playing, weekDays])

  const { chartData, dayLabel } = useMemo(() => {
    if (!seasonData || weekDays <= 0) return { chartData: [], dayLabel: '' }
    const dayIndex = weekStartDay + dayOffset
    const start = dayIndex * 24
    const p = seasonData.policies[policy]
    const rows = []
    for (let i = 0; i < 24; i++) {
      const idx = start + i
      if (idx >= seasonData.timestamps.length) break
      rows.push({
        timestamp: seasonData.timestamps[idx],
        battery_kw: p.battery_kw[idx],
        soc: +(p.soc[idx] * 100).toFixed(2),
      })
    }
    return {
      chartData: rows,
      dayLabel: `${formatDay(seasonData.timestamps[start])} — day ${dayOffset + 1} / ${weekDays}`,
    }
  }, [seasonData, policy, dayOffset, weekStartDay, weekDays])

  return (
    <Card
      title="Season replay"
      subtitle="Scrub through the selected week, one day at a time — battery schedule and state of charge for the selected policy."
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
      {seasonData && weekDays > 0 && (
        <>
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
              <XAxis dataKey="timestamp" tickFormatter={formatHour} interval={2} tick={axisTick} />
              <YAxis
                yAxisId="kw"
                tick={axisTick}
                width={60}
                label={{ value: 'kW', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }}
              />
              <YAxis yAxisId="soc" orientation="right" domain={[0, 100]} tick={axisTick} width={44} unit="%" />
              <Tooltip labelFormatter={formatHour} {...tooltipProps(isDark)} />
              <ReferenceLine yAxisId="kw" y={0} stroke={isDark ? '#69787e' : '#8a9aa0'} />
              <Bar yAxisId="kw" dataKey="battery_kw" name="Battery (kW)" fill={isDark ? BATTERY_COLOR.dark : BATTERY_COLOR.light} radius={[2, 2, 2, 2]} isAnimationActive={false} />
              <Area
                yAxisId="soc"
                type="monotone"
                dataKey="soc"
                name="SOC (%)"
                stroke={isDark ? SOC_COLOR.dark : SOC_COLOR.light}
                fill={isDark ? SOC_COLOR.dark : SOC_COLOR.light}
                fillOpacity={0.12}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Line yAxisId="soc" type="monotone" dataKey="soc" stroke="none" legendType="none" isAnimationActive={false} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>

          <div className="mt-3.5 flex items-center gap-3 border-t border-rail pt-3.5">
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'Pause season replay' : 'Play season replay'}
              className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-full border border-rail bg-surface text-ink transition-colors hover:border-accent hover:text-accent-ink"
            >
              {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            </button>
            <input
              type="range"
              min={0}
              max={Math.max(0, weekDays - 1)}
              value={dayOffset}
              onChange={(e) => setDayOffset(Number(e.target.value))}
              className="flex-1 accent-accent"
              aria-label="Day within week"
            />
            <span className="w-44 flex-none text-right font-mono text-[11px] text-muted">{dayLabel}</span>
          </div>
        </>
      )}
    </Card>
  )
}
