import { useData } from '../lib/useData'
import Card from './Card'
import LoadingError from './LoadingError'

const TARGET_LABELS = {
  solar_mw: 'Solar',
  wind_mw: 'Wind',
  load_mw: 'Load',
}

const MODEL_LABELS = {
  tft: 'TFT',
  lstm: 'LSTM',
  persistence: 'Persistence',
  seasonal_naive: 'Seasonal naive',
  lightgbm: 'LightGBM',
}

export default function MetricsTable() {
  const { data, loading, error } = useData('metrics.json')

  const byTarget = {}
  if (data) {
    for (const row of data.rows) {
      byTarget[row.target] = byTarget[row.target] || []
      byTarget[row.target].push(row)
    }
  }

  return (
    <Card
      title="Forecast accuracy"
      subtitle="RMSE / MAE / nRMSE / R² on the held-out test set — best model per target highlighted"
    >
      <LoadingError loading={loading} error={error} />
      {data && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-rail text-left text-muted">
                <th className="py-2 pr-4 font-medium">Target</th>
                <th className="py-2 pr-4 font-medium">Model</th>
                <th className="py-2 pr-4 font-medium text-right">RMSE</th>
                <th className="py-2 pr-4 font-medium text-right">MAE</th>
                <th className="py-2 pr-4 font-medium text-right">nRMSE</th>
                <th className="py-2 pr-4 font-medium text-right">R²</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(byTarget).map(([target, rows]) => {
                const best = rows.reduce((a, b) => (b.nrmse < a.nrmse ? b : a))
                return rows.map((row) => {
                  const isBest = row.model === best.model
                  return (
                    <tr
                      key={`${target}-${row.model}`}
                      className={
                        isBest
                          ? 'bg-accent-soft font-medium transition-colors'
                          : 'border-b border-rail transition-colors hover:bg-surface-2'
                      }
                    >
                      <td className="py-1.5 pr-4">{TARGET_LABELS[target] || target}</td>
                      <td className="py-1.5 pr-4">
                        {MODEL_LABELS[row.model] || row.model}
                        {isBest && (
                          <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white shadow-sm">
                            best
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{row.rmse}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{row.mae}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{row.nrmse}</td>
                      <td className="py-1.5 pr-4 text-right tabular-nums">{row.r2 != null ? row.r2 : '—'}</td>
                    </tr>
                  )
                })
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
