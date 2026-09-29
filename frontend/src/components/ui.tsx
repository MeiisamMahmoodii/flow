import clsx from 'clsx'
import { Loader2, X } from 'lucide-react'
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { useEffect } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'

const variants: Record<Variant, string> = {
  primary: 'bg-accent-strong text-white hover:bg-accent shadow-lg shadow-violet-900/30',
  secondary: 'bg-ink-800 text-zinc-200 hover:bg-ink-700 border border-ink-700',
  ghost: 'text-zinc-400 hover:text-zinc-100 hover:bg-ink-800',
  danger: 'bg-red-500/10 text-red-300 hover:bg-red-500/20 border border-red-500/30',
  success: 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-900/30',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: 'sm' | 'md'
  loading?: boolean
  icon?: ReactNode
}) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-9 px-3.5 text-sm',
        variants[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}

const fieldBase =
  'w-full rounded-lg border border-ink-700 bg-ink-900 px-3 text-sm text-zinc-100 placeholder:text-zinc-600 ' +
  'focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 transition'

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx(fieldBase, 'h-9', className)} {...rest} />
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx(fieldBase, 'py-2 leading-relaxed', className)} {...rest} />
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={clsx(fieldBase, 'h-9 pr-8', className)} {...rest}>
      {children}
    </select>
  )
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={clsx('block space-y-1.5', className)}>
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</span>
      {children}
      {hint && <span className="block text-xs text-zinc-500">{hint}</span>}
    </label>
  )
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx('rounded-xl border border-ink-700 bg-ink-900/80', className)}>{children}</div>
}

const badgeColors: Record<string, string> = {
  draft: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  approved: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  imaging: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  images_ready: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30',
  done: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  complete: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  drafting: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  running: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  queued: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
  failed: 'bg-red-500/15 text-red-300 border-red-500/30',
  cancelled: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
}

export function Badge({ status, children }: { status?: string; children?: ReactNode }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium',
        badgeColors[status ?? ''] ?? 'bg-ink-800 text-zinc-300 border-ink-700',
      )}
    >
      {children ?? status?.replace('_', ' ')}
    </span>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx('size-4 animate-spin text-accent', className)} />
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
      <div
        className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-400 transition-all duration-300"
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </div>
  )
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className={clsx('max-h-[92vh] w-full overflow-auto rounded-2xl border border-ink-700 bg-ink-900 shadow-2xl', wide ? 'max-w-5xl' : 'max-w-lg')}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-700 px-5 py-3">
          <h3 className="font-semibold text-zinc-100">{title}</h3>
          <Button variant="ghost" size="sm" onClick={onClose} icon={<X className="size-4" />} />
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-ink-700 px-6 py-14 text-center">
      <div className="text-zinc-600">{icon}</div>
      <p className="font-medium text-zinc-300">{title}</p>
      {children && <div className="max-w-md text-sm text-zinc-500">{children}</div>}
    </div>
  )
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
      {error instanceof Error ? error.message : String(error)}
    </p>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}
