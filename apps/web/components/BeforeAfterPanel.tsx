'use client';

import { ArrowRight } from 'lucide-react';
import { cn, num, signed } from '@/lib/format';

export interface ComparisonRow {
  key: string;
  label: string;
  before: number;
  after: number;
  unit: string;
  digits?: number;
  /** Which direction is an improvement. */
  better: 'lower' | 'higher' | 'neutral';
  hint?: string;
}

/**
 * Baseline vs intervention. Both columns always come from the same engine run
 * over the same inputs — that is the only way the delta means anything.
 */
export function BeforeAfterPanel({
  rows,
  beforeLabel = 'Baseline',
  afterLabel = 'AI control',
}: {
  rows: ComparisonRow[];
  beforeLabel?: string;
  afterLabel?: string;
}) {
  return (
    <div className="overflow-hidden rounded-panel border border-base-600">
      <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr] border-b border-base-600 bg-base-850/80 px-2.5 py-1.5">
        <span className="text-[10px] uppercase tracking-wider text-ink-500">Metric</span>
        <span className="text-right text-[10px] uppercase tracking-wider text-ink-400">
          {beforeLabel}
        </span>
        <span className="text-right text-[10px] uppercase tracking-wider text-accent">
          {afterLabel}
        </span>
        <span className="text-right text-[10px] uppercase tracking-wider text-ink-500">Δ</span>
      </div>
      {rows.map((row) => {
        const delta = row.after - row.before;
        const improved =
          row.better === 'neutral'
            ? null
            : row.better === 'lower'
              ? delta < -1e-9
              : delta > 1e-9;
        const pctChange = Math.abs(row.before) > 1e-9 ? (delta / row.before) * 100 : null;
        const digits = row.digits ?? 1;
        return (
          <div
            key={row.key}
            className="grid grid-cols-[1.4fr_1fr_1fr_1fr] items-baseline border-b border-base-700/60 px-2.5 py-1.5 last:border-b-0"
            title={row.hint}
          >
            <span className="truncate text-2xs text-ink-300">{row.label}</span>
            <span className="tabular text-right text-xs text-ink-200">
              {num(row.before, digits)}
              <span className="ml-0.5 text-[10px] text-ink-500">{row.unit}</span>
            </span>
            <span className="tabular text-right text-xs font-semibold text-ink-100">
              {num(row.after, digits)}
              <span className="ml-0.5 text-[10px] text-ink-500">{row.unit}</span>
            </span>
            <span
              className={cn(
                'tabular text-right text-xs font-medium',
                improved === null
                  ? 'text-ink-400'
                  : improved
                    ? 'text-status-normal'
                    : 'text-status-warning',
              )}
            >
              {signed(delta, digits)}
              {pctChange !== null && (
                <span className="ml-1 text-[10px] opacity-80">({signed(pctChange, 0)}%)</span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function TransitionStat({
  label,
  before,
  after,
  unit,
  digits = 1,
  criticalAbove,
}: {
  label: string;
  before: number;
  after: number;
  unit: string;
  digits?: number;
  criticalAbove?: number;
}) {
  const tone = (value: number) =>
    criticalAbove !== undefined && value >= criticalAbove
      ? 'text-status-critical'
      : 'text-ink-100';
  return (
    <div className="rounded-panel border border-base-600 bg-base-850/60 p-2.5">
      <div className="text-[10px] uppercase tracking-wider text-ink-500">{label}</div>
      <div className="mt-1 flex items-center gap-2">
        <span className={cn('tabular text-lg font-semibold', tone(before))}>
          {num(before, digits)}
          <span className="ml-0.5 text-xs font-normal text-ink-500">{unit}</span>
        </span>
        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-accent" />
        <span className={cn('tabular text-lg font-semibold', tone(after))}>
          {num(after, digits)}
          <span className="ml-0.5 text-xs font-normal text-ink-500">{unit}</span>
        </span>
      </div>
    </div>
  );
}
