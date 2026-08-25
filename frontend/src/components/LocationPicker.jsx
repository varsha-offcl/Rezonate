import { useCallback, useEffect, useRef, useState } from 'react'
import { MapPin, Search, X } from 'lucide-react'

const GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'

const PRESETS = [
  { name: 'Berlin', country: 'Germany', lat: 52.52, lon: 13.41, timezone: 'Europe/Berlin' },
  { name: 'Mumbai', country: 'India', lat: 19.08, lon: 72.88, timezone: 'Asia/Kolkata' },
  { name: 'Delhi', country: 'India', lat: 28.61, lon: 77.21, timezone: 'Asia/Kolkata' },
  { name: 'London', country: 'United Kingdom', lat: 51.51, lon: -0.13, timezone: 'Europe/London' },
  { name: 'New York', country: 'United States', lat: 40.71, lon: -74.01, timezone: 'America/New_York' },
  { name: 'Sydney', country: 'Australia', lat: -33.87, lon: 151.21, timezone: 'Australia/Sydney' },
  { name: 'Tokyo', country: 'Japan', lat: 35.68, lon: 139.69, timezone: 'Asia/Tokyo' },
]

export default function LocationPicker({ location, onLocationChange }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const wrapperRef = useRef(null)
  const debounceRef = useRef(null)

  const search = useCallback(async (q) => {
    if (q.length < 2) {
      setResults(PRESETS.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())))
      return
    }
    setLoading(true)
    try {
      const res = await fetch(`${GEOCODE_URL}?name=${encodeURIComponent(q)}&count=8&language=en`)
      const data = await res.json()
      if (data.results) {
        setResults(
          data.results.map((r) => ({
            name: r.name,
            country: r.country ?? '',
            admin: r.admin1 ?? '',
            lat: r.latitude,
            lon: r.longitude,
            timezone: r.timezone,
          }))
        )
      } else {
        setResults([])
      }
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => search(query), 250)
    return () => clearTimeout(debounceRef.current)
  }, [query, open, search])

  useEffect(() => {
    function handleClick(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function select(loc) {
    onLocationChange(loc)
    setQuery('')
    setOpen(false)
  }

  function handleFocus() {
    setOpen(true)
    if (!query) setResults(PRESETS)
  }

  return (
    <div ref={wrapperRef} className="relative">
      <div className="flex items-center gap-2 rounded-lg border border-rail bg-surface px-3 py-2 transition-colors focus-within:border-accent focus-within:ring-2 focus-within:ring-accent-soft">
        <MapPin className="h-4 w-4 flex-none text-muted" />
        {!open && location ? (
          <button
            type="button"
            onClick={() => { setOpen(true); setQuery('') }}
            className="flex flex-1 items-center gap-2 text-left text-sm text-ink"
          >
            <span className="font-medium">{location.name}</span>
            <span className="text-muted">{location.country}</span>
            <span className="font-mono text-xs text-muted-2">
              {location.lat.toFixed(2)}°, {location.lon.toFixed(2)}°
            </span>
          </button>
        ) : (
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={handleFocus}
            placeholder="Search city…"
            className="flex-1 bg-transparent text-sm text-ink placeholder-muted-2 outline-none"
            autoFocus={open}
          />
        )}
        {open ? (
          <button type="button" onClick={() => setOpen(false)} className="text-muted hover:text-ink">
            <X className="h-4 w-4" />
          </button>
        ) : (
          <Search className="h-4 w-4 flex-none text-muted-2" />
        )}
      </div>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-64 overflow-y-auto rounded-xl border border-rail bg-surface shadow-lg">
          {loading && (
            <div className="px-4 py-3 text-sm text-muted">Searching…</div>
          )}
          {!loading && results.length === 0 && query.length >= 2 && (
            <div className="px-4 py-3 text-sm text-muted">No results found</div>
          )}
          {!loading && results.map((r, i) => (
            <button
              key={`${r.lat}-${r.lon}-${i}`}
              type="button"
              onClick={() => select(r)}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-surface-2"
            >
              <MapPin className="h-3.5 w-3.5 flex-none text-muted-2" />
              <div className="flex-1 min-w-0">
                <span className="font-medium text-ink">{r.name}</span>
                {r.admin && <span className="text-muted">, {r.admin}</span>}
                <span className="text-muted"> — {r.country}</span>
              </div>
              <span className="flex-none font-mono text-xs text-muted-2">
                {r.lat.toFixed(2)}°, {r.lon.toFixed(2)}°
              </span>
            </button>
          ))}
          {!loading && !query && (
            <div className="border-t border-rail px-4 py-2 text-[11px] text-muted-2">
              Popular locations — or type to search any city
            </div>
          )}
        </div>
      )}
    </div>
  )
}
