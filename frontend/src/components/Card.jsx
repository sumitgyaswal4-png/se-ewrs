export default function Card({
  title,
  description,
  actions,
  children,
  bodyClassName = '',
  footer,
  className = '',
}) {
  return (
    <section className={`card flex flex-col ${className}`}>
      {(title || actions) && (
        <div className="card-header">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-slate-900">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={`flex-1 ${bodyClassName}`}>{children}</div>
      {footer && <div className="border-t border-slate-200 px-5 py-3">{footer}</div>}
    </section>
  )
}
