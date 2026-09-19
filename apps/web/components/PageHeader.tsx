'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/format';
import { Pill } from './Primitives';

export interface ContextChip {
  label: string;
  value: string;
  tone?: 'neutral' | 'accent' | 'warning' | 'critical' | 'info' | 'violet';
  title?: string;
}

/**
 * Contextual header for a workspace page: what module you are in, what it
 * operates on, and the operational context (source, mode, asset). Restrained
 * on purpose — this is an application, not a landing page.
 */
export function PageHeader({
  module,
  title,
  subtitle,
  chips = [],
  actions,
  className,
}: {
  module: 'BMS' | 'EMS';
  title: string;
  subtitle: string;
  chips?: ContextChip[];
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        'flex h-topbar shrink-0 items-center gap-4 border-b border-base-600/70 bg-base-900/70 px-3',
        className,
      )}
    >
      <div className="flex min-w-0 shrink-0 items-baseline gap-2">
        <span
          className={cn(
            'font-mono text-[11px] font-bold uppercase tracking-[0.12em]',
            module === 'BMS' ? 'text-accent' : 'text-info',
          )}
        >
          {module}
        </span>
        <span className="h-3 w-px bg-base-600" />
        <h1 className="truncate text-[13px] font-semibold tracking-tight text-ink-100">{title}</h1>
        <span className="hidden truncate text-2xs text-ink-500 lg:inline">{subtitle}</span>
      </div>

      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
        {chips.map((chip) => (
          <Pill key={chip.label} tone={chip.tone ?? 'neutral'} title={chip.title}>
            <span className="text-ink-500">{chip.label}</span>
            <span className="font-semibold">{chip.value}</span>
          </Pill>
        ))}
      </div>

      {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
    </header>
  );
}
