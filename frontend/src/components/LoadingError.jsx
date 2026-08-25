export default function LoadingError({ loading, error }) {
  if (loading) {
    return <p className="text-sm text-muted">Loading…</p>
  }
  if (error) {
    return <p className="text-sm text-critical">Failed to load data: {error}</p>
  }
  return null
}
