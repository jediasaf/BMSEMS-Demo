'use client';

import Link from 'next/link';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { ProvenanceBadge } from '@/components/ProvenanceBadge';
import { EmptyNote, ErrorNote, Panel, Pill, Skeleton, Stat } from '@/components/Primitives';
import { clockTime, num, signed } from '@/lib/format';
import type { Series } from '@/lib/types';

const HORIZON_HOURS = 12;
/** The Control Lab horizon this panel summarises. Must be one the API serves. */
const LAB_HOURS = 24;

/**
 * What the forecast says is coming, and what the optimiser would do about it.
 *
 * The overview used to stop at "here is the measured load and what the model
 * expected" -- which is a report, not an operator's screen. An operator's
 * first two questions are what happens next and whether anything should be
 * done, so both are answered above the fold rather than one page away.
 *
 * Nothing new is computed here. The forecast is the same conformalised
 * LightGBM series the chart already draws, read ahead of the replay cursor
 * instead of behind it; the opportunity is the Control Lab's simulated
 * comparison, which is gated and can say no.
 */

type Forward = {
  peak: number;
  at: string;
  lower: number | null;
  upper: number | null;
  hours: number;
  steps: number;
};

/** The highest predicted point between the cursor and `HORIZON_HOURS` later. */
function readAhead(series: Series | undefined, cursor: string | null): Forward | null {
  if (!series || !cursor) return null;
  const from = Date.parse(cursor);
  if (Number.isNaN(from)) return null;
  const until = from + HORIZON_HOURS * 3_600_000;

  let best = -Infinity;
  let index = -1;
  let last = from;
  let steps = 0;
  series.timestamps.forEach((ts, i) => {
    const t = Date.parse(ts);
    if (t <= from || t > until) return;
    const v = series.values[i];
    steps += 1;
    last = Math.max(last, t);
    if (v === null || v === undefined || !Number.isFinite(v)) return;
    if (v > best) {
      best = v;
      index = i;
    }
  });
  if (index < 0) return null;
  return {
    peak: best,
    at: series.timestamps[index]!,
    lower: series.lower?.[index] ?? null,
    upper: series.upper?.[index] ?? null,
    hours: (last - from) / 3_600_000,
    steps,
  };
}

export function ForecastPanel({
  expected,
  cursor,
  currentLoadKw,
}: {
  expected?: Series;
  cursor: string | null;
  currentLoadKw?: number | null;
}) {
  const ahead = readAhead(expected, cursor);

  return (
    <Panel
      title="Forecast"
      subtitle={
        ahead ? `next ${num(ahead.hours, 0)} h · ${ahead.steps} steps` : `next ${HORIZON_HOURS} h`
      }
      actions={
        expected ? <ProvenanceBadge provenance={expected.provenance} align="right" /> : undefined
      }
    >
      {!expected ? (
        <Skeleton className="h-[86px]" />
      ) : !ahead ? (
        <EmptyNote
          title="End of the replay window"
          detail="Move the replay cursor back to see the forecast ahead of it."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <Stat
              label="Predicted peak"
              value={`${num(ahead.peak, 1)} kW`}
              sub={
                currentLoadKw !== null && currentLoadKw !== undefined
                  ? `${signed(ahead.peak - currentLoadKw, 1)} kW vs now`
                  : undefined
              }
              tone="text-status-info"
            />
            <Stat
              label="Expected at"
              value={clockTime(ahead.at)}
              sub={`in ${num(
                (Date.parse(ahead.at) - Date.parse(cursor ?? ahead.at)) / 3_600_000,
                1,
              )} h`}
            />
            <Stat
              label="80% interval"
              value={
                ahead.lower !== null && ahead.upper !== null
                  ? `${num(ahead.lower, 1)}–${num(ahead.upper, 1)}`
                  : '—'
              }
              sub={
                ahead.lower !== null && ahead.upper !== null
                  ? `± ${num((ahead.upper - ahead.lower) / 2, 1)} kW`
                  : 'no interval published'
              }
            />
            <Stat
              label="Now"
              value={
                currentLoadKw !== null && currentLoadKw !== undefined
                  ? `${num(currentLoadKw, 1)} kW`
                  : '—'
              }
              sub="measured at the cursor"
            />
          </div>
          <p className="mt-2.5 border-t border-base-700 pt-1.5 text-3xs leading-relaxed text-ink-600">
            {expected.provenance.notes ?? 'Out-of-sample: trained only on data before the window.'}
          </p>
        </>
      )}
    </Panel>
  );
}

export function OpportunityPanel({
  siteId,
  scenarioId,
}: {
  siteId: string | null;
  scenarioId: string;
}) {
  const lab = useAsync(
    () =>
      siteId
        ? api.bms.controlLab(siteId, LAB_HOURS, scenarioId)
        : Promise.reject(new Error('no site')),
    [siteId, scenarioId],
  );
  const data = lab.data;
  const accepted = data?.acceptance.accepted ?? false;
  const energy = data?.delta_pct.energy_kwh ?? null;
  const peak = data?.delta_pct.peak_kw ?? null;
  const comfort = data?.delta.comfort_violation_kh ?? null;

  return (
    <Panel
      title="Optimisation"
      subtitle={`${LAB_HOURS} h setpoint plan`}
      actions={
        data ? (
          <Pill tone={accepted ? 'accent' : 'warning'} title={data.acceptance.reason}>
            {accepted ? 'Accepted' : 'Rejected'}
          </Pill>
        ) : undefined
      }
    >
      {!data && lab.loading && <Skeleton className="h-[86px]" />}
      {!data && lab.error && <ErrorNote message={lab.error} onRetry={lab.reload} />}
      {data && (
        <>
          <div className="grid grid-cols-3 gap-x-4 gap-y-3">
            <Stat
              label="HVAC energy"
              value={energy === null ? '—' : `${signed(energy, 1)}%`}
              sub={`${num(data.ai_control.kpis.energy_kwh, 0)} vs ${num(
                data.baseline.kpis.energy_kwh,
                0,
              )} kWh`}
              tone={energy !== null && energy < 0 ? 'text-status-normal' : undefined}
            />
            <Stat
              label="HVAC peak"
              value={peak === null ? '—' : `${signed(peak, 1)}%`}
              sub={`${num(data.ai_control.kpis.peak_kw, 1)} vs ${num(
                data.baseline.kpis.peak_kw,
                1,
              )} kW`}
              tone={peak !== null && peak < 0 ? 'text-status-normal' : undefined}
            />
            <Stat
              label="Comfort cost"
              value={comfort === null ? '—' : `${signed(comfort, 2)} K·h`}
              sub={`${num(data.ai_control.kpis.comfort_violation_steps, 0)} steps outside the band`}
              tone={comfort !== null && comfort > 0.5 ? 'text-status-warning' : undefined}
            />
          </div>
          <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-base-700 pt-1.5">
            <span
              className="truncate text-3xs text-ink-600"
              title={`Simulated by ${data.engine_label}. ${data.acceptance.note}`}
            >
              simulated · {data.engine_label} · advisory only
            </span>
            <Link
              href="/bms/control-lab"
              className="focus-ring shrink-0 text-3xs uppercase tracking-[0.08em] text-accent hover:underline"
            >
              Control Lab →
            </Link>
          </div>
        </>
      )}
    </Panel>
  );
}
