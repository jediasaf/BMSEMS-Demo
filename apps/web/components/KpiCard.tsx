'use client';

import { ProvenanceBadge } from './ProvenanceBadge';
import { SEVERITY_STYLE, cn, signed } from '@/lib/format';
import type { KpiValue } from '@/lib/types';

/**
 * Compact KPI tile. Deliberately small: a row of six has to fit above the fold
 * at 1366 px without the numbers losing their weight.
 *
 * Every tile carries a provenance badge, because the whole point of the
 * platform is that you can ask any number where it came from.
 */
export function KpiCard({
  kpi,
  spark,
  onClick,
}: {
  kpi: KpiValue;
  /** Optional trend, drawn as a hairline sparkline. */
  spark?: (number | null)[];
  onClick?: () => void;
}) {
  const severity = SEVERITY_STYLE[kpi.status];
  const alert = kpi.status === 'HIGH' || kpi.status === 'CRITICAL';

  return (
    <div
      className={cn(
        'panel relative px-2.5 py-2',
        alert && 'border-l-[2px]',
        kpi.status === 'CRITICAL' && 'border-l-status-critical',
        kpi.status === 'HIGH' && 'border-l-status-warning',
        onClick && 'cursor-pointer transition-colors hover:border-base-500',
      )}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="label truncate">{kpi.label}</span>
        <ProvenanceBadge provenance={kpi.provenance} size="xs" align="right" />
      </div>

      <div className="mt-1.5 flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div
            className={cn(
              'tabular truncate text-[19px] font-semibold leading-none',
              alert ? severity.text : 'text-ink-100',
            )}
            title={kpi.display ?? undefined}
          >
            {kpi.display ?? '—'}
          </div>
          {kpi.delta !== null && kpi.delta !== undefined && (
            <div className="tabular mt-1 truncate text-3xs text-ink-500">
              <span
                className={cn(
                  'font-medium',
                  kpi.delta > 0 ? 'text-status-warning' : 'text-status-normal',
                )}
              >
                {signed(kpi.delta)}
                {kpi.unit ? ` ${kpi.unit}` : ''}
              </span>{' '}
              {kpi.delta_label}
            </div>
          )}
        </div>
        {spark && spark.some((v) => v !== null) && (
          <Sparkline values={spark} tone={alert ? severity.text : 'text-ink-400'} />
        )}
      </div>
    </div>
  );
}

function Sparkline({ values, tone }: { values: (number | null)[]; tone: string }) {
  const points = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const w = 56;
  const h = 18;
  // Sample to at most ~56 points: one per horizontal pixel is plenty.
  const step = Math.max(1, Math.floor(points.length / w));
  const sampled = points.filter((_, i) => i % step === 0);
  const d = sampled
    .map((v, i) => {
      const x = (i / Math.max(sampled.length - 1, 1)) * w;
      const y = h - ((v - min) / span) * h;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className={cn('shrink-0', tone)}
      aria-hidden
    >
      <path d={d} fill="none" stroke="currentColor" strokeWidth={1} strokeOpacity={0.65} />
    </svg>
  );
}

export function KpiRow({
  kpis,
  sparks,
  columns = 6,
}: {
  kpis: KpiValue[];
  sparks?: Record<string, (number | null)[]>;
  columns?: 4 | 5 | 6;
}) {
  const cols = {
    4: 'sm:grid-cols-2 xl:grid-cols-4',
    5: 'sm:grid-cols-3 xl:grid-cols-5',
    6: 'sm:grid-cols-3 xl:grid-cols-6',
  } as const;
  return (
    <div className={cn('grid grid-cols-2 gap-2', cols[columns])}>
      {kpis.map((kpi) => (
        <KpiCard key={kpi.key} kpi={kpi} spark={sparks?.[kpi.key]} />
      ))}
    </div>
  );
}
