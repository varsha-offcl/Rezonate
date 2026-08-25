import { useData } from '../lib/useData'
import Card from './Card'
import LoadingError from './LoadingError'

const PROPOSED = 'GA→PSO, trust region'

export default function HeadlineStat() {
  const { data, loading, error } = useData('ablation.json')
  const proposed = data?.rows.find((r) => r.config === PROPOSED)

  return (
    <Card title="Headline result">
      <LoadingError loading={loading} error={error} />
      {proposed && (
        <div className="flex flex-wrap items-baseline gap-3.5 py-0.5">
          <span className="font-display text-[44px] font-bold leading-none tracking-tight text-accent-ink">
            {proposed.capture_pct}%
          </span>
          <span className="max-w-[34ch] text-[13px] text-muted">
            of the MILP oracle's perfect-foresight optimum, captured with zero foresight — {PROPOSED} vs. the idle→oracle
            saving over {data.days} representative days ({data.day_range[0]} to {data.day_range[1]}).
          </span>
        </div>
      )}
    </Card>
  )
}
