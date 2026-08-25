import { useMemo } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

function formatDate(ts) {
  const d = new Date(ts)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[d.getMonth()]} ${d.getDate()}`
}

export default function WeekPicker({ seasonData, weekIndex, onWeekChange }) {
  const weeks = useMemo(() => {
    if (!seasonData) return []
    const { timestamps, days } = seasonData
    const totalWeeks = Math.ceil(days / 7)
    const result = []
    for (let w = 0; w < totalWeeks; w++) {
      const startDay = w * 7
      const endDay = Math.min(startDay + 6, days - 1)
      const startTs = timestamps[startDay * 24]
      const endTs = timestamps[endDay * 24]
      result.push({ startDay, endDay, label: `${formatDate(startTs)} – ${formatDate(endTs)}` })
    }
    return result
  }, [seasonData])

  if (!weeks.length) return null

  const totalWeeks = weeks.length

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => onWeekChange(Math.max(0, weekIndex - 1))}
        disabled={weekIndex === 0}
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-rail text-muted transition-colors hover:border-accent hover:text-accent-ink disabled:opacity-30 disabled:hover:border-rail disabled:hover:text-muted"
        aria-label="Previous week"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      <select
        value={weekIndex}
        onChange={(e) => onWeekChange(Number(e.target.value))}
        className="rounded-lg border border-rail bg-surface px-2.5 py-1.5 text-sm text-ink transition-colors hover:border-accent focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft"
      >
        {weeks.map((w, i) => (
          <option key={i} value={i}>
            Week {i + 1}: {w.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => onWeekChange(Math.min(totalWeeks - 1, weekIndex + 1))}
        disabled={weekIndex === totalWeeks - 1}
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-rail text-muted transition-colors hover:border-accent hover:text-accent-ink disabled:opacity-30 disabled:hover:border-rail disabled:hover:text-muted"
        aria-label="Next week"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  )
}
