'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { cursorTimestamp, useDemo } from '@/lib/store';
import { KpiRow } from '@/components/KpiCard';
import { ReplayControl } from '@/components/ReplayControl';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { ErrorNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { SEVERITY_STYLE, cn, clockTime, num, pct, signed } from '@/lib/format';
import type { FacilityRow } from '@/lib/types';

export default function EmsPortfolioPage() {
  const router = useRouter();
  const { emsScenario, setEmsScenario, scenarios, setFacilityId, window: replayWindow, cursor } =
    useDemo();
  const stamp = cursorTimestamp(replayWindow, cursor);

  const portfolio = useAsync(
    () => api.ems.portfolio(emsScenario, stamp ?? undefined),
    [emsScenario, stamp],
  );
  const emsScenarios = scenarios.filter((s) => s.module === 'EMS');
  const data = portfolio.data;

  const openFacility = (facility: FacilityRow) => {
    setFacilityId(facility.facility_id);
    router.push('/ems/network');
  };

  return (
    <div className="space-y-3">
      <Panel
        title="Portfolio"
        subtitle={data ? `${data.facilities.length} metered facilities` : undefined}
        bodyClassName="space-y-2.5"
      >
        <div className="flex flex-wrap items-center gap-3">
          <ScenarioSelector
            scenarios={emsScenarios}
            selected={emsScenario}
            onSelect={setEmsScenario}
          />
          <div className="ml-auto min-w-[20rem] flex-1">
            <ReplayControl />
          </div>
        </div>
      </Panel>

      {portfolio.error && <ErrorNote message={portfolio.error} onRetry={portfolio.reload} />}
      {!data && portfolio.loading && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-[5.5rem]" />
          ))}
        </div>
      )}
      {data && <KpiRow kpis={data.kpis} />}

      <Panel
        title="Facilities"
        subtitle="click a row to open its network"
        bodyClassName="p-0 overflow-x-auto"
      >
        {!data && <Skeleton className="m-3 h-48" />}
        {data && (
          <table className="w-full min-w-[60rem] border-collapse text-2xs">
            <thead>
              <tr className="border-b border-base-600 bg-base-850/70 text-left">
                <Th>Facility</Th>
                <Th align="right">Transformer</Th>
                <Th align="right">Current demand</Th>
                <Th align="right">Expected</Th>
                <Th align="right">Deviation</Th>
                <Th align="right">Predicted peak</Th>
                <Th align="right">Peak at</Th>
                <Th align="right">Loading</Th>
                <Th align="right">Anomalies</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {data.facilities.map((facility) => {
                const severity = SEVERITY_STYLE[facility.severity];
                return (
                  <tr
                    key={facility.facility_id}
                    onClick={() => openFacility(facility)}
                    className="cursor-pointer border-b border-base-700/50 transition-colors hover:bg-base-700/40"
                  >
                    <Td>
                      <span className="font-medium text-ink-100">{facility.name}</span>
                      <span className="ml-1.5 font-mono text-[10px] text-ink-500">
                        {num(facility.surface_m2, 0)} m²
                      </span>
                      {facility.served_by !== 'model' && (
                        <Pill tone="warning" className="ml-1.5" title={facility.model_note}>
                          naive
                        </Pill>
                      )}
                    </Td>
                    <Td align="right" mono>
                      {num(facility.transformer_kva, 0)} kVA
                    </Td>
                    <Td align="right" mono strong>
                      {num(facility.current_demand_kw)} kW
                    </Td>
                    <Td align="right" mono>
                      {facility.expected_demand_kw === null
                        ? '—'
                        : `${num(facility.expected_demand_kw)} kW`}
                    </Td>
                    <Td align="right" mono>
                      <span
                        className={cn(
                          (facility.deviation_kw ?? 0) > 0
                            ? 'text-status-warning'
                            : 'text-status-info',
                        )}
                      >
                        {signed(facility.deviation_kw)}
                        {facility.deviation_pct !== null && (
                          <span className="ml-1 text-ink-500">
                            ({signed(facility.deviation_pct, 0)}%)
                          </span>
                        )}
                      </span>
                    </Td>
                    <Td align="right" mono>
                      {num(facility.predicted_peak_kw)} kW
                    </Td>
                    <Td align="right" mono>
                      {clockTime(facility.predicted_peak_at)}
                    </Td>
                    <Td align="right">
                      <div className="flex items-center justify-end gap-1.5">
                        <div className="h-1 w-14 overflow-hidden rounded-full bg-base-600">
                          <div
                            className={cn(
                              'h-full',
                              facility.predicted_peak_loading_pct >= 100
                                ? 'bg-status-critical'
                                : facility.predicted_peak_loading_pct >= 85
                                  ? 'bg-status-warning'
                                  : 'bg-status-normal',
                            )}
                            style={{
                              width: `${Math.min(facility.predicted_peak_loading_pct, 100)}%`,
                            }}
                          />
                        </div>
                        <span className={cn('tabular font-mono', severity.text)}>
                          {pct(facility.predicted_peak_loading_pct, 0)}
                        </span>
                      </div>
                    </Td>
                    <Td align="right" mono>
                      {facility.active_anomalies > 0 ? (
                        <span className="text-status-warning">{facility.active_anomalies}</span>
                      ) : (
                        <span className="text-ink-600">0</span>
                      )}
                    </Td>
                    <Td>
                      <Pill
                        tone={
                          facility.severity === 'CRITICAL'
                            ? 'critical'
                            : facility.severity === 'HIGH' || facility.severity === 'MEDIUM'
                              ? 'warning'
                              : 'neutral'
                        }
                      >
                        {facility.risk_level}
                      </Pill>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="How to read this table">
        <ul className="space-y-1 text-2xs leading-relaxed text-ink-400">
          <li>
            <span className="text-ink-200">Current demand</span> is DERIVED from the published
            energy counter; injected scenario load is added on top and never netted out of the
            measurement.
          </li>
          <li>
            <span className="text-ink-200">Expected</span> comes from the per-facility forecaster,
            or from a seasonal-naive reference when that model failed its own quality gate — the
            row is marked <span className="text-status-warning">naive</span> when it does.
          </li>
          <li>
            <span className="text-ink-200">Loading</span> is the predicted peak against a
            transformer capacity calibrated by bisection on the load flow, not against{' '}
            <span className="font-mono">kVA × power factor</span>.
          </li>
          <li>
            Transformer ratings are DERIVED from each site&apos;s observed peak by standard sizing
            practice: this dataset publishes no nameplate data, and pretending otherwise would be
            the easiest lie in the whole project.
          </li>
        </ul>
        <Link href="/ems/scenario-lab" className="focus-ring mt-2 inline-block text-2xs text-accent hover:underline">
          Open the Scenario Lab to stress a facility →
        </Link>
      </Panel>
    </div>
  );
}

function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return (
    <th
      className={cn(
        'whitespace-nowrap px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-wider text-ink-500',
        align === 'right' && 'text-right',
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = 'left',
  mono,
  strong,
}: {
  children: React.ReactNode;
  align?: 'left' | 'right';
  mono?: boolean;
  strong?: boolean;
}) {
  return (
    <td
      className={cn(
        'whitespace-nowrap px-2.5 py-1.5 text-ink-300',
        align === 'right' && 'text-right',
        mono && 'tabular font-mono',
        strong && 'font-semibold text-ink-100',
      )}
    >
      {children}
    </td>
  );
}
