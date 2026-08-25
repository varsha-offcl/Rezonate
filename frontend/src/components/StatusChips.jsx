import { useData } from '../lib/useData'

const PROPOSED = 'GA→PSO, trust region'

function Chip({ warn, children }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-rail px-2.5 py-1 font-mono text-[11px] tracking-wide text-muted">
      <span className={`h-1.5 w-1.5 flex-none rounded-full ${warn ? 'bg-live' : 'bg-accent'}`} />
      {children}
    </span>
  )
}

// Real-data equivalent of the concept artifact's top-strip status chips --
// each number comes from the same exported JSON the charts read, not a
// hand-typed placeholder.
export default function StatusChips() {
  const { data: drift } = useData('drift.json')
  const { data: ablation } = useData('ablation.json')

  const proposed = ablation?.rows.find((r) => r.config === PROPOSED)
  const gap = proposed ? (100 - proposed.capture_pct).toFixed(1) : null
  const triggers = drift?.trigger_timestamps.length

  return (
    <div className="flex flex-wrap gap-2">
      <Chip>forecast: nominal</Chip>
      {triggers != null && (
        <Chip warn={triggers > 0}>drift: {triggers} trigger{triggers === 1 ? '' : 's'} / season</Chip>
      )}
      {gap != null && <Chip>oracle gap: {gap}%</Chip>}
    </div>
  )
}
