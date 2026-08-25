// Shared multi-series palette so every chart with more than one non-accent
// line (dispatch, self-learning, data overview) draws from the same
// restrained, desaturated set instead of ad-hoc bright Tailwind primaries --
// the concept artifact only ever used ink/accent/live/critical plus muted
// neutrals, so extra series get muted, not neon, hues to match that feel.
export const SERIES = {
  solar: { light: '#b9791a', dark: '#e3a94d' }, // = live token; warm=sun reads naturally
  wind: { light: '#3f7ea6', dark: '#6fa9c9' },
  battery: { light: '#6b5b95', dark: '#a597c9' },
  grid: { light: '#0d8577', dark: '#4fb3a3' },
  secondary: { light: '#5b6b70', dark: '#93a3aa' }, // muted token; e.g. LSTM, diversity
}

// The concept artifact's axis labels are small, muted, monospace -- almost
// weightless against the chart itself. Recharts defaults to a heavier
// sans-serif tick in the page's ink color, which reads as "cluttered" next
// to the rest of the app's restrained type. These two make every chart's
// ticks/legend match the artifact's quieter chart chrome.
export const axisTick = { fontSize: 11, fill: 'var(--muted-2)', fontFamily: 'var(--font-mono)' }

export const legendStyle = {
  fontSize: 11,
  fontFamily: 'var(--font-mono)',
  color: 'var(--muted)',
  paddingTop: 10,
}

// Recharts' <Tooltip> hardcodes a white content box and leaves the label's
// text color to inherit from the page. In dark mode that inheritance makes
// the label near-white-on-white -- invisible on hover. These props force
// both the box and the label to follow the app's theme; per-series item
// text already gets its own explicit color from recharts (each line/area's
// stroke/fill), so it isn't affected by this bug.
export function tooltipProps(isDark) {
  return {
    contentStyle: {
      backgroundColor: isDark ? '#111b26' : '#ffffff',
      border: `1px solid ${isDark ? 'rgba(231,238,240,.09)' : 'rgba(16,24,32,.10)'}`,
      borderRadius: 8,
      fontSize: 12,
    },
    labelStyle: {
      color: isDark ? '#e7eef0' : '#101820',
      marginBottom: 4,
    },
  }
}
