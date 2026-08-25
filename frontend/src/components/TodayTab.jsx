import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SERIES, axisTick, legendStyle, tooltipProps } from '../lib/chartTheme'
import { useIsDark } from '../lib/useIsDark'
import Card from './Card'

const API_BASE = 'http://127.0.0.1:8000'
const COLORS = SERIES
const LOAD_COLOR = { light: '#101820', dark: '#e7eef0' }
const SOC_COLOR = { light: '#1e9e73', dark: '#33c990' }
const BOUND_COLOR = { light: '#c0442f', dark: '#e2584f' }
const FORECAST_OPACITY = 0.35
const CONV_COLOR = { light: '#1e9e73', dark: '#33c990' }

function formatHour(ts) {
  return `${new Date(ts).getHours()}:00`
}

function CostCard({ label, value, unit = '€', muted }) {
  return (
    <div className={`rounded-xl border border-rail p-4 ${muted ? 'bg-surface' : 'bg-surface-2'}`}>
      <span className="text-xs font-medium uppercase tracking-wide text-muted-2">{label}</span>
      <p className="mt-1 font-display text-xl font-semibold tracking-tight text-ink">
        {unit}{Math.abs(value).toFixed(2)}
        {value < 0 && <span className="ml-1 text-sm font-normal text-accent-ink">(revenue)</span>}
      </p>
    </div>
  )
}

export default function TodayTab({ location }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedDate, setSelectedDate] = useState('')
  const isDark = useIsDark()

  const todayStr = new Date().toISOString().slice(0, 10)
  const maxDate = new Date(Date.now() + 13 * 86400000).toISOString().slice(0, 10)

  const fetchForecast = useCallback(async (date) => {
    if (!location) return
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        lat: location.lat,
        lon: location.lon,
        timezone: location.timezone || 'UTC',
        country: location.country || 'Germany',
      })
      if (date && date !== todayStr) {
        params.set('date', date)
      }
      const res = await fetch(`${API_BASE}/today?${params}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      if (json.error) throw new Error(json.error)
      setData(json)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [location, todayStr])

  useEffect(() => { fetchForecast(selectedDate) }, [fetchForecast, selectedDate])

  const c = (key) => (isDark ? COLORS[key].dark : COLORS[key].light)

  const isFutureDate = selectedDate && selectedDate !== todayStr
  const currentHour = isFutureDate ? 0 : (data?.current_hour ?? 24)

  const dispatchData = data?.timestamps.map((ts, i) => {
    const isPast = i < currentHour
    const base = {
      timestamp: ts,
      load_kw: data.load_kw[i],
    }
    if (isPast) {
      return {
        ...base,
        solar_kw: data.solar_kw[i],
        wind_kw: data.wind_kw[i],
        batteryDischarge: data.battery_kw[i] > 0 ? data.battery_kw[i] : 0,
        batteryCharge: data.battery_kw[i] < 0 ? data.battery_kw[i] : 0,
        gridImport: data.import_kw[i] > 0 ? data.import_kw[i] : 0,
        gridExport: data.export_kw[i] > 0 ? -data.export_kw[i] : 0,
      }
    }
    return {
      ...base,
      fc_solar_kw: data.solar_kw[i],
      fc_wind_kw: data.wind_kw[i],
      fc_batteryDischarge: data.battery_kw[i] > 0 ? data.battery_kw[i] : 0,
      fc_batteryCharge: data.battery_kw[i] < 0 ? data.battery_kw[i] : 0,
      fc_gridImport: data.import_kw[i] > 0 ? data.import_kw[i] : 0,
      fc_gridExport: data.export_kw[i] > 0 ? -data.export_kw[i] : 0,
    }
  }) ?? []

  const socData = data?.soc.map((v, i) => {
    const isPast = i < currentHour
    const ts = i < data.timestamps.length ? data.timestamps[i] : ''
    return isPast
      ? { timestamp: ts, soc: +(v * 100).toFixed(2) }
      : { timestamp: ts, fc_soc: +(v * 100).toFixed(2) }
  }) ?? []

  const weatherData = data?.timestamps.map((ts, i) => {
    const isPast = i < currentHour
    return {
      timestamp: ts,
      ...(isPast
        ? { solar_w_m2: data.weather.solar_w_m2[i], wind_m_s: data.weather.wind_m_s[i] }
        : { fc_solar_w_m2: data.weather.solar_w_m2[i], fc_wind_m_s: data.weather.wind_m_s[i] }),
    }
  }) ?? []

  const nowTs = data && currentHour < data.timestamps.length ? data.timestamps[currentHour] : null

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <input
            type="date"
            value={selectedDate || todayStr}
            min={todayStr}
            max={maxDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="rounded-lg border border-rail bg-surface px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
          />
          {data && (
            <p className="text-sm text-muted">
              <span className="font-medium text-ink">{data.date}</span> — {data.location ?? location?.name ?? 'Unknown'}
              {(!selectedDate || selectedDate === todayStr) && (
                <span className="ml-2 rounded-full border border-rail px-2 py-0.5 text-xs">
                  Now: {currentHour}:00 · solid = elapsed, faded = forecast
                </span>
              )}
              {selectedDate && selectedDate !== todayStr && (
                <span className="ml-2 rounded-full border border-accent bg-accent-soft px-2 py-0.5 text-xs text-accent-ink">
                  Future forecast
                </span>
              )}
            </p>
          )}
        </div>
        <button
          onClick={() => fetchForecast(selectedDate)}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm font-medium text-accent-ink transition-opacity hover:opacity-90 disabled:cursor-progress disabled:opacity-55"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Fetching & optimising…' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-live bg-live-soft p-4 text-sm text-live">
          {error}. Make sure the backend is running:{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            .venv/Scripts/python -m uvicorn src.api:app --port 8000
          </code>
        </div>
      )}

      {loading && !data && (
        <div className="rounded-xl border border-rail bg-surface p-8 text-center text-sm text-muted">
          Fetching weather forecast and running the GA optimiser (~3-5s)…
        </div>
      )}

      {data && (
        <>
          {/* Cost comparison */}
          {data.comparison && (
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-rail bg-surface p-4">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-2">No battery</span>
                <p className="mt-1 font-display text-xl font-semibold tracking-tight text-ink">
                  €{Math.abs(data.comparison.no_battery).toFixed(2)}
                </p>
                <p className="mt-1 text-xs text-muted">Baseline — grid only</p>
              </div>
              <div className="rounded-xl border border-rail bg-surface p-4">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-2">Rule-based</span>
                <p className="mt-1 font-display text-xl font-semibold tracking-tight text-ink">
                  €{Math.abs(data.comparison.rule_based).toFixed(2)}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Simple charge/discharge logic
                </p>
              </div>
              <div className="rounded-xl border border-accent bg-accent-soft p-4">
                <span className="text-xs font-medium uppercase tracking-wide text-accent-ink">GA-optimised ✓</span>
                <p className="mt-1 font-display text-xl font-semibold tracking-tight text-ink">
                  €{Math.abs(data.comparison.ga_optimised).toFixed(2)}
                </p>
                <p className="mt-1 text-xs font-medium text-accent-ink">
                  Saves {data.comparison.saving_vs_idle_pct}% vs no battery · {data.comparison.saving_vs_rule_pct}% vs rule-based
                </p>
              </div>
            </div>
          )}

          {/* Cost breakdown */}
          <div className="grid gap-3 sm:grid-cols-4">
            <CostCard label="Net cost (GA)" value={data.total_cost} />
            <CostCard label="Import cost" value={data.import_cost} muted />
            <CostCard label="Export revenue" value={data.export_revenue} muted />
            <CostCard label="Degradation" value={data.degradation_cost} muted />
          </div>

          {/* Weather forecast */}
          <Card title="Weather" subtitle="Hourly solar irradiance and wind speed from Open-Meteo. Solid = elapsed hours, faded = forecast.">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={weatherData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
                <XAxis dataKey="timestamp" tickFormatter={formatHour} interval={2} tick={axisTick} />
                <YAxis yAxisId="solar" tick={axisTick} width={60} label={{ value: 'W/m²', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }} />
                <YAxis yAxisId="wind" orientation="right" tick={axisTick} width={50} label={{ value: 'm/s', angle: 90, position: 'insideRight', fontSize: 11, fill: 'var(--muted-2)' }} />
                <Tooltip labelFormatter={formatHour} {...tooltipProps(isDark)} />
                <Legend wrapperStyle={legendStyle} />
                {nowTs && <ReferenceLine x={nowTs} stroke={isDark ? '#e7eef0' : '#101820'} strokeDasharray="4 4" label={{ value: 'Now', fill: isDark ? '#e7eef0' : '#101820', fontSize: 11 }} />}
                {/* Elapsed */}
                <Area yAxisId="solar" type="monotone" dataKey="solar_w_m2" name="Solar (W/m²)" stroke="none" fill={c('solar')} fillOpacity={0.7} isAnimationActive={false} />
                <Line yAxisId="wind" type="monotone" dataKey="wind_m_s" name="Wind (m/s)" stroke={c('wind')} strokeWidth={2} dot={false} isAnimationActive={false} />
                {/* Forecast */}
                <Area yAxisId="solar" type="monotone" dataKey="fc_solar_w_m2" name="Solar forecast" stroke="none" fill={c('solar')} fillOpacity={FORECAST_OPACITY} legendType="none" isAnimationActive={false} />
                <Line yAxisId="wind" type="monotone" dataKey="fc_wind_m_s" name="Wind forecast" stroke={c('wind')} strokeWidth={2} strokeDasharray="6 4" dot={false} legendType="none" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>

          {/* Dispatch chart */}
          <Card title="Predicted dispatch" subtitle="GA-optimised battery schedule. Solid = elapsed, faded = planned.">
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={dispatchData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
                <XAxis dataKey="timestamp" tickFormatter={formatHour} interval={2} tick={axisTick} />
                <YAxis tick={axisTick} width={60} label={{ value: 'kW', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }} />
                <Tooltip labelFormatter={formatHour} {...tooltipProps(isDark)} />
                <Legend wrapperStyle={legendStyle} />
                <ReferenceLine y={0} stroke={isDark ? '#69787e' : '#8a9aa0'} />
                {nowTs && <ReferenceLine x={nowTs} stroke={isDark ? '#e7eef0' : '#101820'} strokeDasharray="4 4" />}
                {/* Elapsed */}
                <Area stackId="past" type="monotone" dataKey="solar_kw" name="Solar" stroke="none" fill={c('solar')} fillOpacity={0.85} isAnimationActive={false} />
                <Area stackId="past" type="monotone" dataKey="wind_kw" name="Wind" stroke="none" fill={c('wind')} fillOpacity={0.85} isAnimationActive={false} />
                <Area stackId="past" type="monotone" dataKey="batteryDischarge" name="Battery" stroke="none" fill={c('battery')} fillOpacity={0.85} isAnimationActive={false} />
                <Area stackId="past" type="monotone" dataKey="gridImport" name="Grid" stroke="none" fill={c('grid')} fillOpacity={0.85} isAnimationActive={false} />
                <Area stackId="past" type="monotone" dataKey="batteryCharge" name="Battery charge" legendType="none" stroke="none" fill={c('battery')} fillOpacity={0.85} isAnimationActive={false} />
                <Area stackId="past" type="monotone" dataKey="gridExport" name="Grid export" legendType="none" stroke="none" fill={c('grid')} fillOpacity={0.85} isAnimationActive={false} />
                {/* Forecast */}
                <Area stackId="future" type="monotone" dataKey="fc_solar_kw" name="Solar (forecast)" legendType="none" stroke="none" fill={c('solar')} fillOpacity={FORECAST_OPACITY} isAnimationActive={false} />
                <Area stackId="future" type="monotone" dataKey="fc_wind_kw" name="Wind (forecast)" legendType="none" stroke="none" fill={c('wind')} fillOpacity={FORECAST_OPACITY} isAnimationActive={false} />
                <Area stackId="future" type="monotone" dataKey="fc_batteryDischarge" name="Battery (forecast)" legendType="none" stroke="none" fill={c('battery')} fillOpacity={FORECAST_OPACITY} isAnimationActive={false} />
                <Area stackId="future" type="monotone" dataKey="fc_gridImport" name="Grid (forecast)" legendType="none" stroke="none" fill={c('grid')} fillOpacity={FORECAST_OPACITY} isAnimationActive={false} />
                <Area stackId="future" type="monotone" dataKey="fc_batteryCharge" name="Battery charge (fc)" legendType="none" stroke="none" fill={c('battery')} fillOpacity={FORECAST_OPACITY} isAnimationActive={false} />
                <Area stackId="future" type="monotone" dataKey="fc_gridExport" name="Grid export (fc)" legendType="none" stroke="none" fill={c('grid')} fillOpacity={FORECAST_OPACITY} isAnimationActive={false} />
                <Line type="monotone" dataKey="load_kw" name="Load" stroke={isDark ? LOAD_COLOR.dark : LOAD_COLOR.light} strokeWidth={2.5} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>

          {/* SOC chart */}
          <Card title="Predicted state of charge" subtitle="Solid = elapsed, dashed = forecast.">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={socData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
                <XAxis dataKey="timestamp" tickFormatter={formatHour} interval={2} tick={axisTick} />
                <YAxis domain={[0, 100]} tick={axisTick} width={44} unit="%" />
                <Tooltip labelFormatter={formatHour} {...tooltipProps(isDark)} />
                <ReferenceLine y={20} stroke={isDark ? BOUND_COLOR.dark : BOUND_COLOR.light} strokeDasharray="4 3" />
                <ReferenceLine y={90} stroke={isDark ? BOUND_COLOR.dark : BOUND_COLOR.light} strokeDasharray="4 3" />
                {nowTs && <ReferenceLine x={nowTs} stroke={isDark ? '#e7eef0' : '#101820'} strokeDasharray="4 4" />}
                <Area type="monotone" dataKey="soc" name="SOC (elapsed)" stroke={isDark ? SOC_COLOR.dark : SOC_COLOR.light} fill={isDark ? SOC_COLOR.dark : SOC_COLOR.light} fillOpacity={0.15} strokeWidth={2.5} dot={false} isAnimationActive={false} />
                <Area type="monotone" dataKey="fc_soc" name="SOC (forecast)" stroke={isDark ? SOC_COLOR.dark : SOC_COLOR.light} fill={isDark ? SOC_COLOR.dark : SOC_COLOR.light} fillOpacity={0.06} strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>

          {/* GA Convergence */}
          {data.convergence?.length > 0 && (
            <Card
              title="GA optimisation process"
              subtitle={`The genetic algorithm searched ${data.convergence[data.convergence.length - 1]?.gen ?? '?'} generations (population 100) to find today's optimal battery schedule. The curve shows the best cost found at each step.`}
            >
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data.convergence} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" className="chart-grid" />
                  <XAxis dataKey="gen" tick={axisTick} label={{ value: 'Generation', position: 'insideBottom', offset: -3, fontSize: 11, fill: 'var(--muted-2)' }} />
                  <YAxis tick={axisTick} width={70} label={{ value: 'Best cost (€)', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--muted-2)' }} />
                  <Tooltip {...tooltipProps(isDark)} />
                  <Line type="monotone" dataKey="best" name="Best cost (€)" stroke={isDark ? CONV_COLOR.dark : CONV_COLOR.light} strokeWidth={2.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
              <p className="mt-3 text-xs text-muted">
                Each generation, the GA evolves 100 candidate battery schedules — selecting the best, crossing and mutating them. The cost drops rapidly in early generations as good patterns emerge, then flattens as the optimiser converges on the best schedule it can find.
              </p>
            </Card>
          )}

          {/* Explanation */}
          {data.explanation && (
            <Card title="Why this schedule" subtitle="Plain-language explanation of the optimiser's decisions.">
              <p className="text-sm leading-relaxed text-ink">{data.explanation}</p>
            </Card>
          )}

          <p className="text-xs text-muted-2">
            Weather: live from Open-Meteo.
            Electricity: {data.weather?.country ?? location?.country ?? 'country'} average retail rate
            ({data.weather?.avg_price_eur_mwh ?? '—'} €/MWh avg) with time-of-use shaping.
            Load: temperature-adjusted residential profile.
            Battery: 300 kWh / 100 kW LFP.
          </p>
        </>
      )}
    </div>
  )
}
