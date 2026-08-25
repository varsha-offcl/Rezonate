/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        rail: 'var(--rail-line)',
        ink: 'var(--ink)',
        muted: 'var(--muted)',
        'muted-2': 'var(--muted-2)',
        accent: 'var(--accent)',
        'accent-ink': 'var(--accent-ink)',
        'accent-soft': 'var(--accent-soft)',
        'accent-soft-2': 'var(--accent-soft-2)',
        live: 'var(--live)',
        'live-soft': 'var(--live-soft)',
        critical: 'var(--critical)',
        'critical-soft': 'var(--critical-soft)',
      },
      fontFamily: {
        display: 'var(--font-display)',
        mono: 'var(--font-mono)',
      },
      boxShadow: {
        card: 'var(--shadow)',
      },
    },
  },
  plugins: [],
}
