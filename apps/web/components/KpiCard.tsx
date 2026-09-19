'use client';

import { ProvenanceBadge } from './ProvenanceBadge';
import { SEVERITY_STYLE, cn, signed } from '@/lib/format';
import type { KpiValue } from '@/lib/types';

export function KpiCard({ kpi, compact = false }: { kpi: KpiValue; compact?: boolean }) {
  const severity = SEVERITY_STYLE[kpi.status];
  const showTone = kpi.status === 'HIGH' || kpi.status === 'CRITICAL';

  return (
    <div
      className={cn(
        'panel flex min-w-0 flex-col justify-between gap-2',
        compact ? 'p-2.5' : 'p-3',
        showTone && 'border-l-2',
        kpi.status === 'CRITICAL' && 'border-l-status-critical',
        kpi.status === 'HIGH' && 'border-l-status-warning',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-2xs uppercase tracking-[0.12em] text-ink-400">
          {kpi.label}
        </span>
        <ProvenanceBadge provenance={kpi.provenance} size="xs" showLabel={false} />
      </div>

      <div className="min-w-0">
        <div
          className={cn(
            'tabular truncate font-semibold leading-none',
            compact ? 'text-xl' : 'text-2xl',
            showTone ? severity.text : 'text-ink-100',
          )}
          title={kpi.display ?? undefined}
        >
          {kpi.display ?? '—'}
        </div>
        {kpi.delta !== null && kpi.delta !== undefined && (
          <div className="tabular mt-1 text-2xs text-ink-400">
            <span
              className={cn(
                kpi.delta > 0 ? 'text-status-warning' : 'text-status-normal',
                'font-medium',
              )}
            >
              {signed(kpi.delta)}
              {kpi.unit ? ` ${kpi.unit}` : ''}
            </span>{' '}
            {kpi.delta_label}
          </div>
        )}
      </div>

      {kpi.hint && !compact && (
        <p className="line-clamp-2 text-[10px] leading-snug text-ink-500">{kpi.hint}</p>
      )}
    </div>
  );
}

export function KpiRow({ kpis, compact }: { kpis: KpiValue[]; compact?: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
      {kpis.map((kpi) => (
        <KpiCard key={kpi.key} kpi={kpi} compact={compact} />
      ))}
    </div>
  );
}
