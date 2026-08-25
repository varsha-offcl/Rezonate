import { useEffect, useState } from 'react'

const STORAGE_KEY = 'theme'

function initialTheme() {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

// The single place that decides light vs. dark and persists the user's
// explicit choice. Toggling flips the `dark` class on <html>; every
// `dark:` Tailwind class and every chart's useIsDark() follow from there.
export function useTheme() {
  const [theme, setTheme] = useState(initialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  return [theme, setTheme]
}
