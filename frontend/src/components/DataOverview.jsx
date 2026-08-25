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

const HOURLY_POINT_CAP = 24 * 30 // above this, aggregate to daily means

function toDateInputValue(iso) {
  return iso.slice(0, 10)
}

function formatTick(ts) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function aggregateDaily(rows) {
  const byDay = new Map()
  for (const row of rows) {
    const day = row.timestamp.slice(0, 10)
    if (!byDay.has(day)) byDay.set(day, { timestamp: day, n: 0, solar_mw: 0, wind_mw: 0, load_mw: 0, price_eur_mwh: 0, priceN: 0 })
    const acc = byDay.get(day)
    acc.n += 1
    acc.solar_mw += row.solar_mw ?? 0
    acc.wind_mw += row.wind_mw ?? 0
    acc.load_mw += row.load_mw ?? 0
    if (row.price_eur_mwh != null) {
      acc.price_eur_mwh += row.price_eur_mwh
      acc.priceN += 1
    }
  }
  return Array.from(byDay.values()).map((acc) => ({
    timestamp: acc.timestamp,
    solar_mw: +(acc.solar_mw / acc.n).toFixed(1),
    wind_mw: +(acc.wind_mw / acc.n).toFixed(1),
    load_mw: +(acc.load_mw / acc.n).toFixed(1),
    price_eur_mwh: acc.priceN ? +(acc.price_eur_mwh / acc.priceN).toFixed(2) : null,
  }))
}

export default function DataOverview() {
  const { data, loading, error } = useData('overview.json')
  const isDark = useIsDark()

  const bounds = useMemo(() => {
    if (!data) return null
    return { min: data.timestamps[0], max: data.timestamps[data.timestamps.length - 1] }
  }, [data])

  const defaultStart = useMemo(() => {
    if (!bounds) return ''
    const maxDate = new Date(bounds.max)
    maxDate.setDate(maxDate.getDate() - 30)
    return toDateInputValue(maxDate.toISOString())
  }, [bounds])

  const [start, setStart] = useState(null)
  const [end, setEnd] = useState(null)

  const effectiveStart = start ?? defaultStart
  const effectiveEnd = end ?? (bounds ? toDateInputValue(bounds.max) : '')

  const { rows, aggregated } = useMemo(() => {
    if (!data || !effectiveStart || !effectiveEnd) return { rows: [], aggregated: false }
    const startTs = `${effectiveStart}T00:00:00`
    const endTs = `${effectiveEnd}T23:59:59`

    const out = []
    for (let i = 0; i < data.timestamps.length; i++) {
      const ts = data.timestamps[i]
      if (ts >= startTs && ts <= endTs) {
        out.push({
          timestamp: ts,
          solar_mw: data.solar_mw[i],
          wind_mw: data.wind_mw[i],
          load_mw: data.load_mw[i],
          price_eur_mwh: data.price_eur_mwh[i],
        })
      }
    }
    if (out.length > HOURLY_POINT_CAP) {
      return { rows: aggregateDaily(out), aggregated: true }
    }
    return { rows: out, aggregated: false }
  }, [data, effectiveStart, effectiveEnd])

  return (
    <Card
      title="Data overview"
      subtitle={
        aggregated
          ? 'Solar, wind, load, price — daily average (range > 30 days)'
          : 'Solar, wind, load, price — hourly'
      }
      right={
        bounds && (
          <div className="flex items-center gap-2 text-sm">
            <input
              type="date"
              value={effectiveStart}
              min={toDateInputValue(bounds.min)}
              max={effectiveEnd}
              onChange={(e) => setStart(e.target.value)}
              className="rounded-lg border border-rail bg-surface px-2.5 py-1.5 text-ink transition-colors hover:border-accent focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
            />
            <span className="text-muted-2">to</span>
            <input
              type="date"
              value={effectiveEnd}
              min={effectiveStart}
              max={toDateInputValue(bounds.max)}
              onChange={(e) => setEnd(e.target.value)}
              className="rounded-lg border border-rail bg-surface px-2.5 py-1.5 text-ink transition-colors hover:border-accent focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
            />
          </div>
        )
      }
    >
      <LoadingError loading={loading} error={error} />
      {rows.length > 0 && (
        <ResponsiveContainer width="100%" height={380}>
          <LineChart data={rows} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
            <XAxis dataKey="timestamp" tickFormatter={formatTick} minTickGap={40} tick={axisTick} />
            <YAxis yAxisId="power" tick={axisTick} width={60} />
            <YAxis yAxisId="price" orientation="right" tick={axisTick} width={50} />
            <Tooltip labelFormatter={formatTick} {...tooltipProps(isDark)} />
            <Legend wrapperStyle={legendStyle} />
            <Line yAxisId="power" type="monotone" dataKey="solar_mw" name="Solar (MW)" stroke={isDark ? SERIES.solar.dark : SERIES.solar.light} dot={false} isAnimationActive={false} />
            <Line yAxisId="power" type="monotone" dataKey="wind_mw" name="Wind (MW)" stroke={isDark ? SERIES.wind.dark : SERIES.wind.light} dot={false} isAnimationActive={false} />
            <Line yAxisId="power" type="monotone" dataKey="load_mw" name="Load (MW)" stroke={isDark ? SERIES.secondary.dark : SERIES.secondary.light} dot={false} isAnimationActive={false} />
            <Line yAxisId="price" type="monotone" dataKey="price_eur_mwh" name="Price (EUR/MWh)" stroke={isDark ? '#e2584f' : '#c0442f'} dot={false} isAnimationActive={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}
