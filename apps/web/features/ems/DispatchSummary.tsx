'use client';

import Link from 'next/link';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { EmptyNote, ErrorNote, Panel, Pill, Skeleton, Stat } from '@/components/Primitives';
import { num, signed } from '@/lib/format';

/**
 * What the optimiser would do about the risk on the chart beside it.
 *
 * The portfolio page forecast the problem and then sent the operator to
 * another page for the answer. This is the answer, in four figures: how much
 * peak comes off, what that does to the transformer, how much energy moves
 * rather than disappears, and whether the second load flow accepted it.
 *
 * On a day with no overload the honest answer is that there is nothing to
 * dispatch, and it says that rather than showing a row of zeroes.
 */
/** Below this the optimiser has nothing to do: its target is 3% under the cap,
 *  so a forecast that never approaches 100% cannot produce a dispatch. Asking
 *  it anyway costs a convex solve and two load flows to be told zero. */
const DISPATCH_THRESHOLD_PCT = 97;

export function DispatchSummary({
  facilityId,
  scenarioId,
  peakLoadingPct,
}: {
  facilityId: string | null;
  scenarioId: string;
  peakLoadingPct: number | null;
}) {
  const needed = peakLoadingPct !== null && peakLoadingPct >= DISPATCH_THRESHOLD_PCT;
  const run = useAsync(
    () =>
      facilityId && needed
        ? api.ems.optimise(facilityId, scenarioId)
        : Promise.reject(new Error('no dispatch needed')),
    [facilityId, scenarioId, needed],
  );
  const data = needed ? run.data : null;
  const summary = data?.summary;
  const acted = (summary?.peak_reduction_kw ?? 0) > 0.01;
  const accepted = data?.acceptance?.accepted ?? false;
  // network_before/after are Partial: the load flow can decline to converge,
  // and a panel that renders "undefined%" as a number would be worse than one
  // that says it does not know.
  const before = data?.network_before.transformer_loading_pct ?? null;
  const after = data?.network_after.transformer_loading_pct ?? null;

  return (
    <Panel
      title="Optimisation"
      subtitle="flexible-load dispatch, checked by a load flow"
      actions={
        data && acted ? (
          <Pill tone={accepted ? 'accent' : 'warning'} title={data.acceptance?.reason}>
            {accepted ? 'Accepted' : 'Rejected'}
          </Pill>
        ) : undefined
      }
    >
      {!needed && peakLoadingPct === null && <Skeleton className="h-[86px]" />}
      {!needed && peakLoadingPct !== null && (
        <EmptyNote
          title="Nothing to dispatch"
          detail={`The forecast peak reaches ${num(peakLoadingPct, 1)}% of the transformer's capacity, so there is no constraint to resolve.`}
        />
      )}
      {needed && !data && run.loading && <Skeleton className="h-[86px]" />}
      {needed && !data && run.error && <ErrorNote message={run.error} onRetry={run.reload} />}
      {data && summary && !acted && (
        <EmptyNote
          title="Nothing to dispatch"
          detail="The optimiser found no load worth moving at this instant."
        />
      )}
      {data && summary && acted && (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <Stat
              label="Peak reduction"
              value={`${signed(-summary.peak_reduction_kw, 1)} kW`}
              sub={`${num(summary.baseline_peak_kw, 1)} → ${num(summary.optimised_peak_kw, 1)} kW`}
              tone="text-status-normal"
            />
            <Stat
              label="Transformer"
              value={after === null ? '—' : `${num(after, 1)}%`}
              sub={
                before === null
                  ? 'load flow did not converge'
                  : `from ${num(before, 1)}% of ${num(summary.cap_kw, 0)} kW`
              }
              tone={
                after === null
                  ? undefined
                  : after <= 100
                    ? 'text-status-normal'
                    : 'text-status-critical'
              }
            />
            <Stat
              label="EV energy moved"
              value={`${num(summary.ev_energy_shifted_kwh, 1)} kWh`}
              sub="deferred and recovered, not shed"
            />
            <Stat
              label="HVAC given up"
              value={`${num(summary.hvac_energy_kwh, 1)} kWh`}
              sub="comfort traded for headroom"
            />
          </div>
          <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-base-700 pt-1.5">
            <span
              className="truncate text-3xs text-ink-600"
              title="The dispatch is judged by a second pandapower solve of the post-action network, not by the optimiser's own estimate. Advisory only."
            >
              {summary.solver} · {num(summary.solve_time_s * 1000, 1)} ms · advisory only
            </span>
            <Link
              href="/ems/scenario-lab"
              className="focus-ring shrink-0 text-3xs uppercase tracking-[0.08em] text-accent hover:underline"
            >
              Scenario Lab →
            </Link>
          </div>
        </>
      )}
    </Panel>
  );
}
