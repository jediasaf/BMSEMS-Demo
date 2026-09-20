'use client';

import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/format';
import type { ReactNode } from 'react';

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  flush,
  scrollable,
  collapsible,
  defaultOpen = false,
}: {
  title?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Remove body padding — for tables and charts that manage their own. */
  flush?: boolean;
  /**
   * Set when the body scrolls. It becomes a focusable, named region, so the
   * content is reachable without a pointer.
   */
  scrollable?: boolean;
  /**
   * For content that answers a question rather than reporting a state:
   * caveats, how-to-read notes, method. It is worth having on the page and
   * not worth spending the page's attention budget on until asked.
   */
  collapsible?: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  const shown = !collapsible || open;

  return (
    <section className={cn('panel', className)}>
      {(title || actions) && (
        <header className="panel-head">
          <div className="flex min-w-0 items-baseline gap-2">
            {collapsible ? (
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
                aria-controls={bodyId}
                className="focus-ring flex min-w-0 items-center gap-1.5 rounded-panel text-left"
              >
                <ChevronDown
                  className={cn(
                    'h-3 w-3 shrink-0 text-ink-500 transition-transform',
                    !open && '-rotate-90',
                  )}
                />
                {title && <h2 className="panel-title">{title}</h2>}
              </button>
            ) : (
              title && <h2 className="panel-title">{title}</h2>
            )}
            {subtitle && <span className="panel-sub">{subtitle}</span>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      {shown && (
        <div
          id={bodyId}
          className={cn(
            flush ? 'min-w-0 flex-1' : 'panel-body',
            scrollable && 'focus-ring',
            bodyClassName,
          )}
          {...(scrollable
            ? { tabIndex: 0, role: 'region', 'aria-label': title ?? 'Panel content' }
            : {})}
        >
          {children}
        </div>
      )}
    </section>
  );
}

export function StatusDot({
  tone,
  pulse = false,
  size = 'sm',
}: {
  tone: 'normal' | 'warning' | 'critical' | 'info' | 'idle';
  pulse?: boolean;
  size?: 'sm' | 'md';
}) {
  const colours = {
    normal: 'bg-status-normal',
    warning: 'bg-status-warning',
    critical: 'bg-status-critical',
    info: 'bg-status-info',
    idle: 'bg-status-idle',
  } as const;
  return (
    <span
      className={cn(
        'inline-block shrink-0 rounded-full',
        size === 'sm' ? 'h-[5px] w-[5px]' : 'h-2 w-2',
        colours[tone],
        pulse && 'animate-pulse-dot',
      )}
    />
  );
}

export function Pill({
  children,
  tone = 'neutral',
  className,
  title,
}: {
  children: ReactNode;
  tone?: 'neutral' | 'accent' | 'warning' | 'critical' | 'info' | 'violet';
  className?: string;
  title?: string;
}) {
  const tones = {
    neutral: 'border-base-500/70 bg-base-800/70 text-ink-300',
    accent: 'border-accent/40 bg-accent/10 text-accent',
    warning: 'border-status-warning/40 bg-status-warning/10 text-status-warning',
    critical: 'border-status-critical/45 bg-status-critical/12 text-status-critical',
    info: 'border-status-info/40 bg-status-info/10 text-status-info',
    violet: 'border-prov-simulated/40 bg-prov-simulated/10 text-prov-simulated',
  } as const;
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-pill border px-1.5 py-[1px] text-3xs font-medium uppercase tracking-[0.08em]',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = 'default',
  size = 'md',
  disabled,
  title,
  className,
  type = 'button',
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'default' | 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  disabled?: boolean;
  title?: string;
  className?: string;
  type?: 'button' | 'submit';
}) {
  const variants = {
    default:
      'border-base-500 bg-base-750 text-ink-200 hover:border-base-400 hover:bg-base-700 hover:text-ink-100',
    primary: 'border-accent/50 bg-accent/14 text-accent hover:border-accent/80 hover:bg-accent/22',
    ghost: 'border-transparent text-ink-400 hover:bg-base-800 hover:text-ink-100',
    danger:
      'border-status-critical/50 bg-status-critical/10 text-status-critical hover:bg-status-critical/20',
  } as const;
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'focus-ring inline-flex items-center justify-center gap-1.5 rounded-panel border font-medium transition-colors',
        size === 'sm'
          ? 'px-2 py-[3px] text-3xs uppercase tracking-[0.08em]'
          : 'px-2.5 py-1.5 text-2xs',
        variants[variant],
        disabled && 'cursor-not-allowed opacity-40 hover:bg-transparent',
        className,
      )}
    >
      {children}
    </button>
  );
}

/** A labelled readout. The unit is always separated from the number. */
export function Readout({
  label,
  value,
  unit,
  tone,
  hint,
  size = 'md',
  className,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  tone?: string;
  hint?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}) {
  const sizes = { sm: 'text-xs', md: 'text-[15px]', lg: 'text-xl' } as const;
  return (
    <div className={cn('min-w-0', className)} title={hint}>
      <div className="label truncate">{label}</div>
      <div
        className={cn(
          'tabular mt-[3px] truncate font-semibold leading-none',
          sizes[size],
          tone ?? 'text-ink-100',
        )}
      >
        {value}
        {unit && <span className="ml-1 text-2xs font-normal text-ink-500">{unit}</span>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-panel bg-base-800/70', className)}>
      <div className="absolute inset-y-0 w-1/4 animate-sweep bg-gradient-to-r from-transparent via-base-700/60 to-transparent" />
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-panel border border-status-critical/40 bg-status-critical/[0.07] p-2.5">
      <div className="min-w-0 flex-1">
        <div className="text-2xs font-semibold uppercase tracking-[0.08em] text-status-critical">
          Panel unavailable
        </div>
        <div className="mt-1 break-words font-mono text-3xs text-ink-400">{message}</div>
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

/** A labelled figure with an optional second line: the unit of a summary row. */
export function Stat({
  label,
  value,
  sub,
  tone,
  title,
}: {
  label: string;
  value: string;
  sub?: ReactNode;
  tone?: string;
  title?: string;
}) {
  return (
    <div className="min-w-0" title={title}>
      <div className="label truncate">{label}</div>
      <div
        className={cn(
          'tabular mt-1 truncate text-[19px] font-semibold leading-none',
          tone ?? 'text-ink-100',
        )}
      >
        {value}
      </div>
      {sub && <div className="tabular mt-1 truncate text-3xs text-ink-500">{sub}</div>}
    </div>
  );
}

export function EmptyNote({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-panel border border-dashed border-base-600 bg-base-800/40 px-3 py-4 text-center">
      <div className="text-2xs font-medium text-ink-200">{title}</div>
      {detail && <div className="mt-1 text-3xs leading-relaxed text-ink-500">{detail}</div>}
    </div>
  );
}

/** Horizontal share bar used in contributor lists and loading gauges. */
export function Meter({
  value,
  max = 100,
  mark,
  tone = 'accent',
  className,
}: {
  value: number;
  max?: number;
  /** Draws a tick at this value — a limit the bar is allowed to run past. */
  mark?: number;
  tone?: 'accent' | 'info' | 'warning' | 'critical' | 'idle';
  className?: string;
}) {
  const tones = {
    accent: 'bg-accent',
    info: 'bg-status-info',
    warning: 'bg-status-warning',
    critical: 'bg-status-critical',
    idle: 'bg-status-idle',
  } as const;
  const scale = (v: number) => Math.max(0, Math.min((v / Math.max(max, 1e-9)) * 100, 100));
  const pct = scale(value);
  return (
    <div
      className={cn('relative h-[3px] w-full overflow-hidden rounded-full bg-base-700', className)}
    >
      <div
        className={cn('h-full transition-[width] duration-300', tones[tone])}
        style={{ width: `${pct}%` }}
      />
      {mark !== undefined && mark < max && (
        <span
          aria-hidden
          className="absolute inset-y-0 w-px bg-ink-300/70"
          style={{ left: `${scale(mark)}%` }}
        />
      )}
    </div>
  );
}

/** Key/value line used throughout detail panels. */
export function Field({
  label,
  value,
  mono,
  tone,
  title,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  tone?: string;
  title?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[3px]" title={title}>
      <span className="shrink-0 text-2xs text-ink-500">{label}</span>
      <span
        className={cn('tabular truncate text-2xs', mono && 'font-mono', tone ?? 'text-ink-100')}
      >
        {value}
      </span>
    </div>
  );
}
