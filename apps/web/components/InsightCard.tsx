'use client';

import { AlertTriangle, ChevronRight } from 'lucide-react';
import { ProvenanceBadge } from './ProvenanceBadge';
import { Pill, StatusDot } from './Primitives';
import { SEVERITY_STYLE, cn, num, signed, clockTime, fullTimestamp } from '@/lib/format';
import type { Insight } from '@/lib/types';

export const KIND_LABEL: Record<string, string> = {
  OVER_CONSUMPTION: 'Over-consumption',
  UNDER_CONSUMPTION: 'Under-consumption',
  OFF_HOURS_LOAD: 'Out-of-hours load',
  FLATLINE: 'Flatline',
  SENSOR_DRIFT: 'Sensor drift',
  MISSING_DATA: 'Missing data',
  PEAK_EXCURSION: 'Peak excursion',
};

/** Compact row for the chronological feed. Selection drives the detail pane. */
export function InsightRow({
  insight,
  active,
  onClick,
}: {
  insight: Insight;
  active?: boolean;
  onClick?: () => void;
}) {
  const severity = SEVERITY_STYLE[insight.severity];
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'focus-ring group relative flex w-full items-start gap-2 border-b border-base-700/60 px-2.5 py-2 text-left transition-colors last:border-b-0',
        active ? 'bg-accent/[0.07]' : 'hover:bg-base-800/70',
      )}
    >
      <span
        className={cn(
          'absolute inset-y-0 left-0 w-[2px]',
          active
            ? 'bg-accent'
            : insight.severity === 'CRITICAL'
              ? 'bg-status-critical'
              : insight.severity === 'HIGH' || insight.severity === 'MEDIUM'
                ? 'bg-status-warning'
                : 'bg-transparent',
        )}
      />
      <span className="tabular mt-[1px] shrink-0 font-mono text-2xs text-ink-500">
        {clockTime(insight.timestamp)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <StatusDot
            tone={
              insight.severity === 'CRITICAL'
                ? 'critical'
                : insight.severity === 'HIGH' || insight.severity === 'MEDIUM'
                  ? 'warning'
                  : 'idle'
            }
          />
          <span className="truncate text-3xs font-semibold uppercase tracking-[0.08em] text-ink-300">
            {KIND_LABEL[insight.kind] ?? insight.kind}
          </span>
        </span>
        <span className="mt-0.5 block truncate text-2xs text-ink-200">{insight.title}</span>
      </span>
      <span className="tabular shrink-0 text-right">
        <span className={cn('block text-2xs font-semibold', severity.text)}>
          {num(insight.confidence * 100, 0)}%
        </span>
        <span className="block text-3xs text-ink-600">conf</span>
      </span>
      <ChevronRight className="mt-[2px] h-3 w-3 shrink-0 text-ink-600 group-hover:text-ink-300" />
    </button>
  );
}

/** Full detail for the selected insight: what, how far off, and what to check. */
export function InsightDetail({ insight }: { insight: Insight }) {
  const severity = SEVERITY_STYLE[insight.severity];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="tabular font-mono text-2xs text-ink-400">
          {fullTimestamp(insight.timestamp)}
        </span>
        <Pill
          tone={
            insight.severity === 'CRITICAL'
              ? 'critical'
              : insight.severity === 'HIGH' || insight.severity === 'MEDIUM'
                ? 'warning'
                : 'neutral'
          }
        >
          {severity.label}
        </Pill>
        <Pill tone="neutral">{KIND_LABEL[insight.kind] ?? insight.kind}</Pill>
        {insight.zone_id && <Pill tone="info">{insight.zone_id}</Pill>}
        <span className="ml-auto">
          <ProvenanceBadge provenance={insight.provenance} size="xs" />
        </span>
      </div>

      <h3 className="text-sm font-semibold leading-snug text-ink-100">{insight.title}</h3>

      <div className="grid grid-cols-3 gap-px overflow-hidden rounded-panel border border-base-600 bg-base-600">
        <Cell label="Observed" value={`${num(insight.observed)} ${insight.unit}`} />
        <Cell label="Expected" value={`${num(insight.expected)} ${insight.unit}`} />
        <Cell
          label="Deviation"
          value={`${signed(insight.deviation)} ${insight.unit}`}
          sub={
            insight.deviation_pct !== null && insight.deviation_pct !== undefined
              ? `${signed(insight.deviation_pct, 0)}%`
              : undefined
          }
          tone={(insight.deviation ?? 0) > 0 ? 'text-status-warning' : 'text-status-info'}
        />
      </div>

      <p className="text-2xs leading-relaxed text-ink-300">{insight.description}</p>

      <div>
        <div className="label mb-1">Evidence</div>
        <div className="rounded-panel border border-base-600 bg-base-800/60 px-2.5 py-1.5">
          {insight.evidence.map((item) => (
            <div
              key={item.feature}
              className="flex items-baseline justify-between gap-3 border-b border-base-700/50 py-1 last:border-b-0"
            >
              <span className="min-w-0 flex-1 text-2xs leading-tight text-ink-400">
                {item.label}
              </span>
              <span className="shrink-0 text-right">
                <span className="tabular font-mono text-2xs text-ink-100">
                  {num(item.contribution, 2)}
                </span>
                {item.detail && (
                  <span className="block text-3xs leading-tight text-ink-600">{item.detail}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="label mb-1 flex items-center gap-1.5">
          <AlertTriangle className="h-3 w-3 text-status-warning" />
          Possible causes
          <span className="normal-case tracking-normal text-ink-600">— not a diagnosis</span>
        </div>
        <ul className="space-y-0.5">
          {insight.possible_causes.map((cause) => (
            <li key={cause} className="flex gap-1.5 text-2xs leading-relaxed text-ink-300">
              <span className="shrink-0 text-ink-600">·</span>
              <span>{cause}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-panel border border-base-600 bg-base-800/70 p-2.5">
        <div className="label mb-1">Recommended next step</div>
        <p className="text-2xs leading-relaxed text-ink-200">{insight.recommended_next_step}</p>
      </div>
    </div>
  );
}

function Cell({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="bg-base-850 px-2.5 py-2">
      <div className="label truncate">{label}</div>
      <div className={cn('tabular mt-1 truncate text-sm font-semibold', tone ?? 'text-ink-100')}>
        {value}
      </div>
      {sub && <div className="tabular text-3xs text-ink-400">{sub}</div>}
    </div>
  );
}
