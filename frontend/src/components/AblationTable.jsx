import { useData } from '../lib/useData'
import Card from './Card'
import LoadingError from './LoadingError'

// The two rows to call out: the perfect-foresight ceiling, and the design the
// project actually proposes.
const ORACLE = 'MILP oracle'
const PROPOSED = 'GA→PSO, trust region'

function rowClass(config) {
  if (config === PROPOSED)
    return 'bg-accent-soft font-medium'
  if (config === ORACLE)
    return 'bg-surface-2 italic text-muted'
  return 'border-b border-rail'
}

export default function AblationTable() {
  const { data, loading, error } = useData('ablation.json')

  return (
    <Card
      title="Ablation: which design captures the most saving"
      subtitle={
        data
          ? `${data.days} representative days across the season. "Capture" = share of the idle→oracle saving each configuration achieves (100% = perfect-foresight ceiling). Lower cost is better.`
          : undefined
      }
    >
      {loading && <LoadingError loading={loading} error={null} />}
      {!loading && error && (
        <p className="text-sm text-muted">
          Available once the ablation has run — run{' '}
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">
            python -m src.eval.ablation
          </code>{' '}
          then re-export.
        </p>
      )}
      {data && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-rail text-left text-muted">
                <th className="py-2 pr-4 font-medium">Configuration</th>
                <th className="py-2 pr-4 text-right font-medium">Cost (€)</th>
                <th className="py-2 pr-4 text-right font-medium">Capture</th>
                <th className="py-2 pr-4 text-right font-medium">Degradation (€)</th>
                <th className="py-2 pr-4 text-right font-medium">Violations</th>
                <th className="py-2 pr-4 text-right font-medium">Gens</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.config} className={`${rowClass(r.config)} transition-colors`}>
                  <td className="py-1.5 pr-4">
                    {r.config}
                    {r.config === PROPOSED && (
                      <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                        proposed
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">{r.total_cost.toLocaleString()}</td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">
                    {r.capture_pct == null ? '—' : `${r.capture_pct}%`}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">{r.degradation}</td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">
                    {r.violation_days > 0 ? (
                      <span className="text-critical">{r.violation_days}d</span>
                    ) : (
                      '0'
                    )}
                  </td>
                  <td className="py-1.5 pr-4 text-right tabular-nums">{r.mean_gens_to_converge ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">
            Idle (no battery) €{data.idle_cost.toLocaleString()} → oracle ceiling €{data.oracle_cost.toLocaleString()}
            {' '}over these {data.days} days. Comparison rows isolate each ingredient: GA-only vs GA→PSO shows what
            intraday correction adds; unbounded vs trust-region shows what the bound adds; TFT vs LSTM vs persistence
            shows the value of the forecast.
          </p>
        </div>
      )}
    </Card>
  )
}
