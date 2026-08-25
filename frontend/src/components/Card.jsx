export default function Card({ title, subtitle, right, children }) {
  return (
    <section className="rounded-2xl border border-rail bg-surface p-5 shadow-card transition-shadow sm:p-7">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight text-ink">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}
