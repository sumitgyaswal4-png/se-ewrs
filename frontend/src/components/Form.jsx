/** Accessible form primitives.
 *
 * Each control gets a real <label for>, and an error is wired to the
 * input through aria-describedby + aria-invalid so a screen reader
 * announces the problem rather than just the field name.
 */

import { useId } from 'react'

export function Field({ label, error, hint, required, children, className = '' }) {
  const id = useId()
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={className}>
      <label htmlFor={id} className="label">
        {label}
        {required && (
          <span className="ml-0.5 text-risk-high" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children({
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': describedBy || undefined,
        'aria-required': required || undefined,
      })}
      {hint && !error && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs font-medium text-risk-high">
          {error}
        </p>
      )}
    </div>
  )
}

export function TextInput({ label, error, hint, required, className, ...props }) {
  return (
    <Field label={label} error={error} hint={hint} required={required} className={className}>
      {(a11y) => <input className="input" {...a11y} {...props} />}
    </Field>
  )
}

export function TextArea({ label, error, hint, required, className, rows = 3, ...props }) {
  return (
    <Field label={label} error={error} hint={hint} required={required} className={className}>
      {(a11y) => <textarea className="input" rows={rows} {...a11y} {...props} />}
    </Field>
  )
}

export function SelectInput({
  label,
  error,
  hint,
  required,
  className,
  options = [],
  placeholder,
  ...props
}) {
  return (
    <Field label={label} error={error} hint={hint} required={required} className={className}>
      {(a11y) => (
        <select className="input" {...a11y} {...props}>
          {placeholder && <option value="">{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  )
}

/** A filter control for the toolbar row above a table or chart. */
export function FilterSelect({ label, value, onChange, options, placeholder = 'All' }) {
  const id = useId()
  return (
    <div className="min-w-[9rem]">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-500">
        {label}
      </label>
      <select
        id={id}
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

export function FilterDate({ label, value, onChange }) {
  const id = useId()
  return (
    <div className="min-w-[9rem]">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-500">
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800"
      />
    </div>
  )
}
