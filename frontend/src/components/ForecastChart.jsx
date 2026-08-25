import { useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
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

const TARGET_LABELS = {
  solar_mw: 'Solar generation (MW)',
  wind_mw: 'Wind generation (MW)',
  load_mw: 'Load (MW)',
}

// Each model's median line: which row key holds its prediction, its label,
// whether it carries a P10–P90 band, and its colour in light/dark themes.
const MODELS = {
  tft: { key: 'tft_p50', label: 'TFT', band: true, color: { light: '#1e9e73', dark: '#33c990' }, width: 2.5 },
  lstm: { key: 'lstm', label: 'LSTM', band: false, color: SERIES.battery, width: 2 },
  lightgbm: { key: 'lightgbm', label: 'LightGBM', band: false, color: SERIES.wind, width: 2 },
  seasonal_naive: { key: 'seasonal_naive', label: 'Seasonal naive', band: false, color: SERIES.solar, width: 1.5 },
  persistence: { key: 'persistence', label: 'Persistence', band: false, color: SERIES.secondary, width: 1.5 },
}
const MODEL_ORDER = ['tft', 'lstm', 'lightgbm', 'seasonal_naive', 'persistence']

const ACTUAL_COLOR = { light: '#101820', dark: '#e7eef0' }

function formatTick(ts) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:00`
}

export default function ForecastChart() {
  const { data, loading, error } = useData('forecast.json')
  const [target, setTarget] = useState('load_mw')
  const [model, setModel] = useState('tft')
  const isDark = useIsDark()

  const series = data?.[target]

  // Only offer models actually present in the exported data (so the chart
  // still works on a Phase-1 baseline-only export, before the TFT is trained).
  const available = useMemo(() => {
    if (!series?.length) return []
    const sample = series.find((row) => Object.keys(row).length > 2) || series[0]
    return MODEL_ORDER.filter((m) => {
      if (m === 'tft') return sample.tft_p50 != null
      return sample[MODELS[m].key] != null
    })
  }, [series])

  // Fall back to a present model if the selected one isn't in this export.
  const activeModel = available.includes(model) ? model : available[0]
  const cfg = activeModel ? MODELS[activeModel] : null

  const chartData = useMemo(() => {
    if (!series) return []
    return series.map((row) => ({
      ...row,
      tft_band: row.tft_p10 != null && row.tft_p90 != null ? [row.tft_p10, row.tft_p90] : null,
    }))
  }, [series])

  return (
    <Card
      title="Forecast: actual vs. model"
      subtitle="Held-out test window, 24h-ahead day-ahead forecasts. The TFT shows its P10–P90 quantile band."
      right={
        data && (
          <div className="flex flex-wrap gap-2">
            <select
              value={activeModel ?? ''}
              onChange={(e) => setModel(e.target.value)}
              className="rounded-lg border border-rail bg-surface px-2.5 py-1.5 text-sm text-ink transition-colors hover:border-accent focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
            >
              {available.map((m) => (
                <option key={m} value={m}>{MODELS[m].label}</option>
              ))}
            </select>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="rounded-lg border border-rail bg-surface px-2.5 py-1.5 text-sm text-ink transition-colors hover:border-accent focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
            >
              {Object.keys(data).map((key) => (
                <option key={key} value={key}>{TARGET_LABELS[key] || key}</option>
              ))}
            </select>
          </div>
        )
      }
    >
      <LoadingError loading={loading} error={error} />
      {data && cfg && (
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
            <XAxis dataKey="timestamp" tickFormatter={formatTick} minTickGap={40} tick={axisTick} />
            <YAxis tick={axisTick} width={60} />
            <Tooltip labelFormatter={formatTick} {...tooltipProps(isDark)} />
            <Legend wrapperStyle={legendStyle} />
            {cfg.band && (
              <Area
                type="monotone"
                dataKey="tft_band"
                name="TFT P10–P90"
                stroke="none"
                fill={isDark ? cfg.color.dark : cfg.color.light}
                fillOpacity={0.18}
                isAnimationActive={false}
                connectNulls
              />
            )}
            <Line
              type="monotone"
              dataKey="actual"
              name="Actual"
              stroke={isDark ? ACTUAL_COLOR.dark : ACTUAL_COLOR.light}
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey={cfg.key}
              name={cfg.band ? `${cfg.label} (P50)` : cfg.label}
              stroke={isDark ? cfg.color.dark : cfg.color.light}
              strokeWidth={cfg.width}
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}
