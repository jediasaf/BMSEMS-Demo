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
      <div className="grid grid-cols-[1.5fr_0.95fr_0.95fr_1fr] border-b border-base-600 bg-base-800/80 px-2.5 py-1.5">
        <span className="label">Metric</span>
        <span className="label text-right">{beforeLabel}</span>
        <span className="label text-right text-accent">{afterLabel}</span>
        <span className="label text-right">Δ</span>
      </div>
      {rows.map((row) => {
        const delta = row.after - row.before;
        const improved =
          row.better === 'neutral' ? null : row.better === 'lower' ? delta < -1e-9 : delta > 1e-9;
        const pctChange = Math.abs(row.before) > 1e-9 ? (delta / row.before) * 100 : null;
        const digits = row.digits ?? 1;
        return (
          <div
            key={row.key}
            className="grid grid-cols-[1.5fr_0.95fr_0.95fr_1fr] items-baseline border-b border-base-700/60 px-2.5 py-[7px] last:border-b-0"
            title={row.hint}
          >
            <span className="pr-2 text-2xs leading-tight text-ink-400">{row.label}</span>
            <span className="tabular text-right text-xs text-ink-200">
              {num(row.before, digits)}
              <span className="ml-0.5 text-3xs text-ink-600">{row.unit}</span>
            </span>
            <span className="tabular text-right text-xs font-semibold text-ink-100">
              {num(row.after, digits)}
              <span className="ml-0.5 text-3xs text-ink-600">{row.unit}</span>
            </span>
            <span
              className={cn(
                'tabular pl-2 text-right text-xs font-medium',
                improved === null
                  ? 'text-ink-400'
                  : improved
                    ? 'text-status-normal'
                    : 'text-status-warning',
              )}
            >
              {signed(delta, digits)}
              {pctChange !== null && (
                <span className="ml-1 text-3xs opacity-80">({signed(pctChange, 0)}%)</span>
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
  testId,
}: {
  label: string;
  before: number;
  after: number;
  unit: string;
  digits?: number;
  criticalAbove?: number;
  /** Prefix for the before/after test hooks the e2e demo test reads. */
  testId?: string;
}) {
  const tone = (value: number) =>
    criticalAbove !== undefined && value >= criticalAbove ? 'text-status-critical' : 'text-ink-100';
  return (
    <div className="rounded-panel border border-base-600 bg-base-800/60 px-2.5 py-2">
      <div className="label">{label}</div>
      <div className="mt-1 flex items-center gap-2">
        <span
          data-testid={testId && `${testId}-before`}
          className={cn('tabular text-base font-semibold', tone(before))}
        >
          {num(before, digits)}
          <span className="ml-0.5 text-3xs font-normal text-ink-600">{unit}</span>
        </span>
        <ArrowRight className="h-3 w-3 shrink-0 text-accent" />
        <span
          data-testid={testId && `${testId}-after`}
          className={cn('tabular text-base font-semibold', tone(after))}
        >
          {num(after, digits)}
          <span className="ml-0.5 text-3xs font-normal text-ink-600">{unit}</span>
        </span>
      </div>
    </div>
  );
}
