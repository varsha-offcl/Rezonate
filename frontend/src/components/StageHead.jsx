export default function StageHead({ title, description }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 className="font-display text-[26px] font-semibold leading-tight tracking-tight text-ink">{title}</h2>
        <p className="mt-1 max-w-[62ch] text-[14px] text-muted">{description}</p>
      </div>
      <span className="flex-none whitespace-nowrap rounded-lg bg-accent-soft px-2.5 py-1 font-mono text-[11px] tracking-wide text-accent-ink">
        live data
      </span>
    </div>
  )
}
