'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { cursorTimestamp, useDemo } from '@/lib/store';
import { Workspace } from '@/components/AppShell';
import { PageHeader } from '@/components/PageHeader';
import { KpiRow } from '@/components/KpiCard';
import { ReplayControl } from '@/components/ReplayControl';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { DataSourcePanel } from '@/components/DataSourcePanel';
import { ErrorNote, Meter, Panel, Pill, Skeleton } from '@/components/Primitives';
import { SEVERITY_STYLE, cn, clockTime, num, pct, signed } from '@/lib/format';
import type { FacilityRow, Provenance, Series } from '@/lib/types';

export default function EmsPortfolioPage() {
  const router = useRouter();
  const {
    emsScenario,
    setEmsScenario,
    scenarios,
    setFacilityId,
    window: replayWindow,
    cursor,
    status,
  } = useDemo();
  const stamp = cursorTimestamp(replayWindow, cursor);

  const portfolio = useAsync(
    () => api.ems.portfolio(emsScenario, stamp ?? undefined),
    [emsScenario, stamp],
  );
  const data = portfolio.data;

  const open = (facility: FacilityRow) => {
    setFacilityId(facility.facility_id);
    router.push('/ems/network');
  };

  const totalDemand = data?.facilities.reduce((sum, f) => sum + f.current_demand_kw, 0) ?? 0;
  const atRisk = data?.facilities.filter((f) => f.predicted_peak_loading_pct >= 85).length ?? 0;

  return (
    <>
      <PageHeader
        module="EMS"
        title="AI Power Operator"
        subtitle="Measured → forecast → risk → optimise → resolve"
        chips={[
          { label: 'Source', value: status?.data_label ?? '…' },
          { label: 'Facilities', value: String(data?.facilities.length ?? '…') },
          {
            label: 'At risk',
            value: String(atRisk),
            tone: atRisk > 0 ? 'warning' : 'neutral',
          },
          { label: 'Network', value: 'pandapower · ready', tone: 'info' },
        ]}
      />

      <Workspace>
        <div className="space-y-2.5">
          <div className="panel flex flex-row flex-wrap items-center gap-x-4 gap-y-2 px-2.5 py-2">
            <div className="flex items-center gap-2">
              <span className="label shrink-0">Scenario</span>
              <ScenarioSelector
                scenarios={scenarios.filter((s) => s.module === 'EMS')}
                selected={emsScenario}
                onSelect={setEmsScenario}
              />
            </div>
            <span className="hidden h-4 w-px bg-base-600 lg:block" />
            <div className="flex min-w-[26rem] max-w-[40rem] flex-1 items-center gap-2.5">
              <span className="label shrink-0">Replay</span>
              <div className="min-w-0 flex-1">
                <ReplayControl />
              </div>
            </div>
          </div>

          {portfolio.error && <ErrorNote message={portfolio.error} onRetry={portfolio.reload} />}
          {!data && portfolio.loading ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-[72px]" />
              ))}
            </div>
          ) : (
            data && <KpiRow kpis={data.kpis} columns={5} />
          )}

          <div className="grid gap-2.5 xl:grid-cols-[1.9fr_1fr]">
            <PortfolioDemandPanel scenarioId={emsScenario} totalDemand={totalDemand} />
            <DataSourcePanel />
          </div>

          <Panel
            title="Facility performance"
            subtitle="click a row to open its network"
            flush
            bodyClassName="overflow-x-auto"
          >
            {!data && <Skeleton className="m-2.5 h-48" />}
            {data && (
              <table className="tech-table min-w-[62rem]">
                <thead>
                  <tr>
                    <th>Facility</th>
                    <th className="text-right">Transformer</th>
                    <th className="text-right">Current</th>
                    <th className="text-right">Expected</th>
                    <th className="text-right">Deviation</th>
                    <th className="text-right">Predicted peak</th>
                    <th className="text-right">At</th>
                    <th>Loading</th>
                    <th className="text-right">Anomalies</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.facilities.map((facility) => {
                    const severity = SEVERITY_STYLE[facility.severity];
                    const tone =
                      facility.predicted_peak_loading_pct >= 100
                        ? 'critical'
                        : facility.predicted_peak_loading_pct >= 85
                          ? 'warning'
                          : 'accent';
                    return (
                      <tr
                        key={facility.facility_id}
                        onClick={() => open(facility)}
                        className="cursor-pointer transition-colors hover:bg-base-800/70"
                      >
                        <td>
                          <span className="font-medium text-ink-100">{facility.name}</span>
                          <span className="ml-1.5 font-mono text-3xs text-ink-600">
                            {num(facility.surface_m2, 0)} m²
                          </span>
                          {facility.served_by !== 'model' && (
                            <Pill tone="warning" className="ml-1.5" title={facility.model_note}>
                              naive
                            </Pill>
                          )}
                        </td>
                        <td className="tabular text-right font-mono">
                          {num(facility.transformer_kva, 0)} kVA
                        </td>
                        <td className="tabular text-right font-mono font-semibold text-ink-100">
                          {num(facility.current_demand_kw)} kW
                        </td>
                        <td className="tabular text-right font-mono">
                          {facility.expected_demand_kw === null
                            ? '—'
                            : `${num(facility.expected_demand_kw)} kW`}
                        </td>
                        <td className="tabular text-right font-mono">
                          <span
                            className={cn(
                              (facility.deviation_kw ?? 0) > 0
                                ? 'text-status-warning'
                                : 'text-status-info',
                            )}
                          >
                            {signed(facility.deviation_kw)}
                            {facility.deviation_pct !== null && (
                              <span className="ml-1 text-ink-600">
                                ({signed(facility.deviation_pct, 0)}%)
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="tabular text-right font-mono">
                          {num(facility.predicted_peak_kw)} kW
                        </td>
                        <td className="tabular text-right font-mono text-ink-500">
                          {clockTime(facility.predicted_peak_at)}
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            <Meter
                              value={facility.predicted_peak_loading_pct}
                              tone={tone}
                              className="w-16"
                            />
                            <span className={cn('tabular font-mono', severity.text)}>
                              {pct(facility.predicted_peak_loading_pct, 0)}
                            </span>
                          </div>
                        </td>
                        <td className="tabular text-right font-mono">
                          {facility.active_anomalies > 0 ? (
                            <span className="text-status-warning">{facility.active_anomalies}</span>
                          ) : (
                            <span className="text-ink-600">0</span>
                          )}
                        </td>
                        <td>
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
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Panel>

          <Panel title="How to read this table">
            <ul className="grid gap-1.5 text-2xs leading-relaxed text-ink-400 lg:grid-cols-2">
              <li>
                <span className="text-ink-200">Current demand</span> is DERIVED from the published
                energy counter; injected scenario load is added on top and never netted out of the
                measurement.
              </li>
              <li>
                <span className="text-ink-200">Expected</span> comes from the per-facility
                forecaster, or from a seasonal-naive reference when that model failed its own
                quality gate — the row is marked <span className="text-status-warning">naive</span>{' '}
                when it does.
              </li>
              <li>
                <span className="text-ink-200">Loading</span> is the predicted peak against a
                transformer capacity calibrated by bisection on the load flow, not against{' '}
                <span className="font-mono">kVA × power factor</span>.
              </li>
              <li>
                Transformer ratings are DERIVED from each site&apos;s observed peak by standard
                sizing practice: this dataset publishes no nameplate data, and pretending otherwise
                would be the easiest lie in the whole project.
              </li>
            </ul>
            <Link
              href="/ems/scenario-lab"
              className="focus-ring mt-2 inline-block text-3xs uppercase tracking-[0.08em] text-accent hover:underline"
            >
              Open the Scenario Lab to stress a facility →
            </Link>
          </Panel>
        </div>
      </Workspace>
    </>
  );
}

/** Portfolio demand: the lead facility's forward horizon against its capacity. */
function PortfolioDemandPanel({
  scenarioId,
  totalDemand,
}: {
  scenarioId: string;
  totalDemand: number;
}) {
  const risk = useAsync(() => api.ems.risk(undefined, scenarioId), [scenarioId]);
  const data = risk.data;

  const configs: ChartSeriesConfig[] = useMemo(() => {
    if (!data) return [];
    const forecastProv: Provenance = data.provenance.forecast;
    const injectedProv: Provenance = {
      ...forecastProv,
      source_type: 'INJECTED',
      source_key: 'scenario_engine',
      source_name: 'EcoTwin scenario engine',
      publisher: 'EcoTwin AI',
      processing: 'seeded scenario disturbance added on top of the measurement',
    };
    const mk = (id: string, label: string, values: number[], prov: Provenance): Series => ({
      series_id: id,
      label,
      unit: 'kW',
      timestamps: data.timestamps,
      values,
      provenance: prov,
    });
    const out: ChartSeriesConfig[] = [
      { series: mk('forecast', 'Forecast demand', data.forecast_kw, forecastProv), width: 1.5 },
    ];
    if (data.injected_kw.some((v) => v > 0.01)) {
      out.push({
        series: mk('injected', 'Injected load', data.injected_kw, injectedProv),
        width: 1.2,
        area: true,
      });
      out.push({
        series: mk(
          'total',
          'Total at the transformer',
          data.forecast_kw.map((v, i) => v + (data.injected_kw[i] ?? 0)),
          injectedProv,
        ),
        colour: '#e6f0ee',
        width: 1.8,
      });
    }
    return out;
  }, [data]);

  return (
    <Panel
      title="Demand against capacity"
      subtitle={
        data ? `Site ${data.facility_id} · ${data.horizon_minutes / 60} h horizon` : undefined
      }
      actions={
        <span className="tabular font-mono text-3xs text-ink-500">
          portfolio {num(totalDemand, 0)} kW
        </span>
      }
      flush
      className="min-h-[300px]"
    >
      {risk.error && (
        <div className="p-2.5">
          <ErrorNote message={risk.error} onRetry={risk.reload} />
        </div>
      )}
      {data ? (
        <TimeSeriesChart
          configs={configs}
          height={266}
          yAxisName="kW"
          markLineValue={data.cap_kw}
          markLineLabel={`${num(data.cap_kw, 0)} kW = 100% transformer loading`}
        />
      ) : (
        <Skeleton className="m-2.5 h-[260px]" />
      )}
    </Panel>
  );
}
