import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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

// Human-readable names for the raw covariate identifiers.
const VAR_LABELS = {
  solar_mw: 'Solar (history)',
  wind_mw: 'Wind (history)',
  load_mw: 'Load (history)',
  shortwave_radiation: 'Shortwave radiation',
  direct_radiation: 'Direct radiation',
  temperature_2m: 'Temperature 2m',
  cloudcover: 'Cloud cover',
  windspeed_100m: 'Wind speed 100m',
  winddirection_100m: 'Wind direction 100m',
  hour_sin: 'Hour (sin)',
  hour_cos: 'Hour (cos)',
  dow_sin: 'Day-of-week (sin)',
  dow_cos: 'Day-of-week (cos)',
  month_sin: 'Month (sin)',
  month_cos: 'Month (cos)',
  time_idx: 'Time index',
  relative_time_idx: 'Relative time',
  encoder_length: 'Encoder length',
}

const label = (name) => VAR_LABELS[name] || name

export default function VariableImportance() {
  const { data, loading, error } = useData('importance.json')
  const [view, setView] = useState('encoder')
  const isDark = useIsDark()

  const rows = (data?.[view] || []).map((d) => ({
    name: label(d.name),
    importance: +(d.importance * 100).toFixed(1),
  }))
  const height = Math.max(200, rows.length * 30 + 30)

  return (
    <Card
      title="TFT variable importance"
      subtitle="Variable-selection weights from the Temporal Fusion Transformer — the share of attention each input receives."
      right={
        data && (
          <div className="inline-flex rounded-lg border border-rail p-0.5">
            {[
              ['encoder', 'Past inputs'],
              ['decoder', 'Known-future inputs'],
            ].map(([key, text]) => (
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
          Available once the TFT is trained — run{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            python -m src.forecasting.tft
          </code>{' '}
          then re-export, and this chart populates from the model's
          variable-selection weights.
        </p>
      )}
      {data && (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={rows} layout="vertical" margin={{ top: 5, right: 30, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} className="chart-grid" />
            <XAxis type="number" unit="%" tick={axisTick} />
            <YAxis type="category" dataKey="name" width={130} tick={axisTick} />
            <Tooltip formatter={(v) => [`${v}%`, 'Importance']} {...tooltipProps(isDark)} />
            <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
              {rows.map((_, i) => (
                <Cell key={i} fill={isDark ? '#33c990' : '#1e9e73'} fillOpacity={1 - (i / (rows.length + 2))} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  )
}
