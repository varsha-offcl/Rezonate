import { useState } from 'react'
import { Moon, Sprout, Sun } from 'lucide-react'
import AblationTable from './components/AblationTable'
import ConvergenceChart from './components/ConvergenceChart'
import DataOverview from './components/DataOverview'
import DriftChart from './components/DriftChart'
import DispatchChart from './components/DispatchChart'
import ExplanationCard from './components/ExplanationCard'
import ForecastChart from './components/ForecastChart'
import HeadlineStat from './components/HeadlineStat'
import LocationPicker from './components/LocationPicker'
import MetricsTable from './components/MetricsTable'
import PsoOverlayChart from './components/PsoOverlayChart'
import ScheduleChart from './components/ScheduleChart'
import SeasonReplay from './components/SeasonReplay'
import SelfLearningChart from './components/SelfLearningChart'
import SocChart from './components/SocChart'
import StageHead from './components/StageHead'
import StatusChips from './components/StatusChips'
import TodayTab from './components/TodayTab'
import WeekPicker from './components/WeekPicker'
import ChatBox from './components/ChatBox'
import WhatIfPanel from './components/WhatIfPanel'
import VariableImportance from './components/VariableImportance'
import { useData } from './lib/useData'
import { useTheme } from './lib/useTheme'

const DEFAULT_LOCATION = { name: 'Berlin', country: 'Germany', lat: 52.52, lon: 13.41, timezone: 'Europe/Berlin' }

const STAGES = [
  { id: 'today', cadence: 'Live · now', title: 'Today' },
  { id: 'forecast', cadence: 'Once daily · 18:00', title: 'Forecast' },
  { id: 'schedule', cadence: 'Once daily · 18:30', title: 'Day-ahead schedule' },
  { id: 'live', cadence: 'Every 15 min', title: 'Live ops' },
  { id: 'results', cadence: 'End of season', title: 'Results' },
]

function Pair({ children }) {
  return <div className="grid gap-5 md:grid-cols-2">{children}</div>
}

export default function App() {
  const [theme, setTheme] = useTheme()
  const [stage, setStage] = useState('today')
  const [weekIndex, setWeekIndex] = useState(0)
  const [location, setLocation] = useState(DEFAULT_LOCATION)
  const { data: seasonData } = useData('season.json')

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-4 py-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 flex-none items-center justify-center rounded-[10px] bg-accent-soft text-accent-ink">
              <Sprout className="h-5 w-5" />
            </div>
            <div>
              <h1 className="font-display text-xl font-semibold leading-tight tracking-tight text-ink">
                Renewable Energy Optimizer
              </h1>
              <p className="mt-0.5 text-sm text-muted">
                Forecast → Schedule → Live Ops → Season Results
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <StatusChips />
            <button
              type="button"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              className="flex h-10 w-10 flex-none items-center justify-center rounded-lg border border-rail text-muted transition-colors hover:border-accent hover:text-accent-ink"
            >
              {theme === 'dark' ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
            </button>
          </div>
        </div>

        {/* Location picker — visible on all tabs */}
        <div className="mb-5">
          <LocationPicker location={location} onLocationChange={setLocation} />
        </div>

        <nav
          role="tablist"
          aria-label="Pipeline stage"
          className="mb-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-rail bg-rail sm:grid-cols-5"
        >
          {STAGES.map((s) => {
            const active = stage === s.id
            return (
              <button
                key={s.id}
                role="tab"
                aria-selected={active}
                onClick={() => setStage(s.id)}
                className={`flex flex-col gap-1.5 bg-surface px-5 py-4 text-left transition-colors hover:bg-surface-2 ${
                  active ? 'shadow-[inset_0_-2px_0_var(--accent)]' : ''
                }`}
              >
                <span className={`font-mono text-[11px] uppercase tracking-wide ${active ? 'text-accent-ink' : 'text-muted-2'}`}>
                  {s.cadence}
                </span>
                <span className="font-display text-base font-semibold tracking-tight text-ink">{s.title}</span>
              </button>
            )
          })}
        </nav>

        <main className="flex flex-col gap-10">
          {stage === 'today' && (
            <section>
              <StageHead
                title="Today's predicted schedule"
                description="Live weather forecast from Open-Meteo → GA optimiser → predicted battery dispatch for today. Requires the backend server."
              />
              <TodayTab location={location} />
            </section>
          )}

          {stage === 'forecast' && (
            <section>
              <StageHead
                title="24h-ahead forecast"
                description="TFT reads the last 168 hours and today's weather to forecast tomorrow's solar, wind, and load — with a P10–P90 uncertainty band the scheduler hedges against."
              />
              <div className="flex flex-col gap-5">
                <ForecastChart />
                <Pair>
                  <MetricsTable />
                  <VariableImportance />
                </Pair>
              </div>
            </section>
          )}

          {stage === 'schedule' && (
            <section>
              <StageHead
                title="Day-ahead dispatch schedule"
                description="The GA searches 24 hours of battery setpoints against tomorrow's forecast — population 100, warm-started from yesterday's elite chromosomes."
              />
              <Pair>
                <ConvergenceChart />
                <ScheduleChart />
              </Pair>
            </section>
          )}

          {stage === 'live' && (
            <section>
              <StageHead
                title="Live correction over the season"
                description="PSO re-tunes the dispatch within a trust region once actuals diverge from the forecast. Use the week picker to explore different parts of the season."
              />
              <div className="flex flex-col gap-5">
                <div className="flex items-center justify-between">
                  <WeekPicker seasonData={seasonData} weekIndex={weekIndex} onWeekChange={setWeekIndex} />
                </div>
                <DispatchChart seasonData={seasonData} weekIndex={weekIndex} />
                <Pair>
                  <SocChart seasonData={seasonData} weekIndex={weekIndex} />
                  <PsoOverlayChart />
                </Pair>
                <SeasonReplay seasonData={seasonData} weekIndex={weekIndex} />
                <Pair>
                  <SelfLearningChart />
                  <DriftChart />
                </Pair>
                <ExplanationCard />
                <WhatIfPanel />
              </div>
            </section>
          )}

          {stage === 'results' && (
            <section>
              <StageHead
                title="Season results"
                description="Every configuration benchmarked against a MILP oracle under perfect foresight — the headline number is the share of that ceiling this design actually captures."
              />
              <div className="flex flex-col gap-5">
                <HeadlineStat />
                <AblationTable />
                <DataOverview />
              </div>
            </section>
          )}
        </main>

        <footer className="mt-12 font-mono text-xs text-muted-2">
          Source: Open Power System Data (Germany) + Open-Meteo (Berlin weather archive).
        </footer>
      </div>

      <ChatBox />
    </div>
  )
}
