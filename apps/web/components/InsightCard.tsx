'use client';

import { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import { ProvenanceBadge } from './ProvenanceBadge';
import { Pill } from './Primitives';
import { SEVERITY_STYLE, cn, num, signed, fullTimestamp } from '@/lib/format';
import type { Insight } from '@/lib/types';

const KIND_LABEL: Record<string, string> = {
  OVER_CONSUMPTION: 'Over-consumption',
  UNDER_CONSUMPTION: 'Under-consumption',
  OFF_HOURS_LOAD: 'Out-of-hours load',
  FLATLINE: 'Flatline',
  SENSOR_DRIFT: 'Sensor drift',
  MISSING_DATA: 'Missing data',
  PEAK_EXCURSION: 'Peak excursion',
};

export function InsightCard({
  insight,
  defaultOpen = false,
  onSimulate,
}: {
  insight: Insight;
  defaultOpen?: boolean;
  onSimulate?: () => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const severity = SEVERITY_STYLE[insight.severity];

  return (
    <article
      className={cn(
        'rounded-panel border border-base-600/70 bg-base-800/60 transition-colors hover:border-base-500',
        insight.severity === 'CRITICAL' && 'border-l-2 border-l-status-critical',
        insight.severity === 'HIGH' && 'border-l-2 border-l-status-warning',
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="focus-ring flex w-full items-start gap-2.5 p-2.5 text-left"
      >
        <span className="mt-0.5 shrink-0">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-ink-400" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-ink-400" />
          )}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
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
          </span>
          <span className="mt-1 block truncate text-xs font-medium text-ink-100">
            {insight.title}
          </span>
        </span>

        <span className="tabular shrink-0 text-right">
          <span className={cn('block text-sm font-semibold', severity.text)}>
            {num(insight.confidence * 100, 0)}%
          </span>
          <span className="block text-[10px] text-ink-500">confidence</span>
        </span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-base-700 px-2.5 pb-3 pt-2.5">
          <div className="grid grid-cols-3 gap-2 rounded-panel bg-base-850/70 p-2">
            <Readout label="Observed" value={`${num(insight.observed)} ${insight.unit}`} />
            <Readout label="Expected" value={`${num(insight.expected)} ${insight.unit}`} />
            <Readout
              label="Deviation"
              value={`${signed(insight.deviation)} ${insight.unit}`}
              tone={
                (insight.deviation ?? 0) > 0 ? 'text-status-warning' : 'text-status-info'
              }
              sub={
                insight.deviation_pct !== null && insight.deviation_pct !== undefined
                  ? `${signed(insight.deviation_pct, 0)}%`
                  : undefined
              }
            />
          </div>

          <p className="text-2xs leading-relaxed text-ink-300">{insight.description}</p>

          <div>
            <h4 className="text-[10px] uppercase tracking-wider text-ink-500">Evidence</h4>
            <ul className="mt-1 space-y-1">
              {insight.evidence.map((item) => (
                <li
                  key={item.feature}
                  className="flex items-baseline justify-between gap-2 text-2xs"
                >
                  <span className="truncate text-ink-300">{item.label}</span>
                  <span className="tabular shrink-0 font-mono text-ink-100">
                    {num(item.contribution, 2)}
                    {item.detail && <span className="ml-1 text-ink-500">{item.detail}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-500">
              <AlertTriangle className="h-3 w-3 text-status-warning" />
              Possible causes
              <span className="normal-case tracking-normal text-ink-500">
                — not a diagnosis
              </span>
            </h4>
            <ul className="mt-1 space-y-0.5">
              {insight.possible_causes.map((cause) => (
                <li key={cause} className="flex gap-1.5 text-2xs text-ink-300">
                  <span className="text-ink-500">·</span>
                  <span>{cause}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-panel border border-base-600 bg-base-850/60 p-2">
            <div className="text-[10px] uppercase tracking-wider text-ink-500">
              Recommended next step
            </div>
            <p className="mt-0.5 text-2xs leading-relaxed text-ink-200">
              {insight.recommended_next_step}
            </p>
          </div>

          <div className="flex items-center justify-between gap-2 pt-0.5">
            <ProvenanceBadge provenance={insight.provenance} size="xs" />
            {onSimulate && (
              <button
                type="button"
                onClick={onSimulate}
                className="focus-ring text-2xs font-medium text-accent hover:underline"
              >
                Test an action in Control Lab →
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function Readout({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone?: string;
  sub?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-ink-500">{label}</div>
      <div className={cn('tabular truncate text-xs font-semibold', tone ?? 'text-ink-100')}>
        {value}
      </div>
      {sub && <div className="tabular text-[10px] text-ink-400">{sub}</div>}
    </div>
  );
}
