'use client';

import { cn } from '@/lib/format';
import type { ReactNode } from 'react';

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn('panel flex min-w-0 flex-col', className)}>
      {(title || actions) && (
        <header className="panel-header">
          <div className="flex min-w-0 items-baseline gap-2">
            {title && <h2 className="panel-title truncate">{title}</h2>}
            {subtitle && <span className="truncate text-2xs text-ink-400">{subtitle}</span>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn('min-w-0 flex-1 p-3', bodyClassName)}>{children}</div>
    </section>
  );
}

export function StatusDot({
  tone,
  pulse = false,
}: {
  tone: 'normal' | 'warning' | 'critical' | 'info' | 'idle';
  pulse?: boolean;
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
        'inline-block h-1.5 w-1.5 shrink-0 rounded-full',
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
    neutral: 'border-base-500/70 bg-base-700/60 text-ink-300',
    accent: 'border-accent/40 bg-accent/10 text-accent',
    warning: 'border-status-warning/40 bg-status-warning/10 text-status-warning',
    critical: 'border-status-critical/40 bg-status-critical/10 text-status-critical',
    info: 'border-status-info/40 bg-status-info/10 text-status-info',
    violet: 'border-prov-simulated/40 bg-prov-simulated/10 text-prov-simulated',
  } as const;
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 rounded-pill border px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wider',
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
      'border-base-500 bg-base-700/80 text-ink-200 hover:border-base-400 hover:bg-base-600/80',
    primary:
      'border-accent/50 bg-accent/15 text-accent hover:border-accent/80 hover:bg-accent/25',
    ghost: 'border-transparent bg-transparent text-ink-300 hover:bg-base-700/70 hover:text-ink-100',
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
        size === 'sm' ? 'px-2 py-1 text-2xs' : 'px-2.5 py-1.5 text-xs',
        variants[variant],
        disabled && 'cursor-not-allowed opacity-45 hover:bg-transparent',
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Metric({
  label,
  value,
  unit,
  tone,
  hint,
  className,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  tone?: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={cn('min-w-0', className)} title={hint}>
      <div className="truncate text-2xs uppercase tracking-wider text-ink-400">{label}</div>
      <div className={cn('tabular mt-0.5 truncate text-lg font-semibold', tone ?? 'text-ink-100')}>
        {value}
        {unit && <span className="ml-1 text-xs font-normal text-ink-400">{unit}</span>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-panel bg-base-700/50', className)}>
      <div className="absolute inset-y-0 w-1/3 animate-sweep bg-gradient-to-r from-transparent via-base-600/50 to-transparent" />
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-panel border border-status-critical/40 bg-status-critical/10 p-3">
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-status-critical">Could not load this panel</div>
        <div className="mt-1 break-words text-2xs text-ink-300">{message}</div>
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyNote({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded-panel border border-dashed border-base-500/70 bg-base-800/40 p-4 text-center">
      <div className="text-xs font-medium text-ink-200">{title}</div>
      {detail && <div className="mt-1 text-2xs leading-relaxed text-ink-400">{detail}</div>}
    </div>
  );
}
