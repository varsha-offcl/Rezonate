import { useEffect, useState } from 'react'

// Reads the live `dark` class on <html> rather than `prefers-color-scheme`
// directly, so charts follow the manual theme toggle (useTheme.js) too, not
// just the OS setting.
export function useIsDark() {
  const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'))

  useEffect(() => {
    const el = document.documentElement
    const observer = new MutationObserver(() => setIsDark(el.classList.contains('dark')))
    observer.observe(el, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  return isDark
}
