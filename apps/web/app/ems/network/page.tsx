'use client';

import { useEffect } from 'react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { cursorTimestamp, useDemo } from '@/lib/store';
import { NetworkDiagram, NetworkViolations } from '@/components/NetworkDiagram';
import { ReplayControl } from '@/components/ReplayControl';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { ProvenanceBadge } from '@/components/ProvenanceBadge';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { ErrorNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { DataQualityDrawer } from '@/features/bms/DataQualityDrawer';
import { cn, fullTimestamp, num, pct } from '@/lib/format';
import type { Provenance, Series } from '@/lib/types';

export default function PowerNetworkPage() {
  const { facilityId, setFacilityId, emsScenario, setEmsScenario, scenarios, window: replayWindow, cursor } =
    useDemo();
  const stamp = cursorTimestamp(replayWindow, cursor);

  const facilities = useAsync(() => api.ems.facilities(), []);
  useEffect(() => {
    if (facilities.data && !facilityId) setFacilityId(facilities.data.default_facility_id);
  }, [facilities.data, facilityId, setFacilityId]);

  const network = useAsync(
    () =>
      facilityId
        ? api.ems.network(facilityId, emsScenario, stamp ?? undefined)
        : Promise.reject(new Error('no facility')),
    [facilityId, emsScenario, stamp],
  );
  const risk = useAsync(
    () =>
      facilityId
        ? api.ems.risk(facilityId, emsScenario, stamp ?? undefined)
        : Promise.reject(new Error('no facility')),
    [facilityId, emsScenario, stamp],
  );

  const emsScenarios = scenarios.filter((s) => s.module === 'EMS');
  const data = network.data;
  const riskData = risk.data;

  const riskConfigs: ChartSeriesConfig[] = riskData
    ? (() => {
        const forecastProv: Provenance = riskData.provenance.forecast;
        const injectedProv: Provenance = {
          ...forecastProv,
          source_type: 'INJECTED',
          source_key: 'scenario_engine',
          source_name: 'EcoTwin scenario engine',
          publisher: 'EcoTwin AI',
          processing: 'seeded scenario disturbance added on top of the measurement',
        };
        const total = riskData.forecast_kw.map((value, index) => value + (riskData.injected_kw[index] ?? 0));
        const mk = (id: string, label: string, values: number[], prov: Provenance): Series => ({
          series_id: id,
          label,
          unit: 'kW',
          timestamps: riskData.timestamps,
          values,
          provenance: prov,
        });
        const configs: ChartSeriesConfig[] = [
          { series: mk('forecast', 'Forecast demand', riskData.forecast_kw, forecastProv), width: 1.5 },
        ];
        if (riskData.injected_kw.some((value) => value > 0.01)) {
          configs.push({
            series: mk('injected', 'Injected load', riskData.injected_kw, injectedProv),
            width: 1.3,
            area: true,
          });
          configs.push({
            series: mk('total', 'Total at the transformer', total, injectedProv),
            colour: '#e8eef5',
            width: 1.9,
          });
        }
        return configs;
      })()
    : [];

  return (
    <div className="space-y-3">
      <Panel
        title="Power network"
        subtitle={data ? `facility ${data.facility_id} · ${fullTimestamp(data.at)}` : undefined}
        actions={facilityId ? <DataQualityDrawer assetId={facilityId} module="ems" /> : undefined}
        bodyClassName="space-y-2.5"
      >
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-2xs text-ink-400">
            Facility
            <select
              value={facilityId ?? ''}
              onChange={(event) => setFacilityId(event.target.value)}
              className="focus-ring rounded-panel border border-base-500 bg-base-700 px-1.5 py-1 text-2xs text-ink-100"
            >
              {facilities.data?.facilities.map((facility) => (
                <option key={String(facility.facility_id)} value={String(facility.facility_id)}>
                  {String(facility.name)}
                </option>
              ))}
            </select>
          </label>
          <div className="ml-auto min-w-[20rem] flex-1">
            <ReplayControl />
          </div>
        </div>
        <ScenarioSelector
          scenarios={emsScenarios}
          selected={emsScenario}
          onSelect={setEmsScenario}
        />
      </Panel>

      {network.error && <ErrorNote message={network.error} onRetry={network.reload} />}

      <div className="grid gap-3 xl:grid-cols-[1.5fr_1fr]">
        <Panel
          title="Single line diagram"
          subtitle="pandapower AC load flow"
          actions={data ? <ProvenanceBadge provenance={data.provenance} size="xs" /> : undefined}
          bodyClassName="p-1"
        >
          {data ? <NetworkDiagram network={data} height={330} /> : <Skeleton className="h-[330px]" />}
        </Panel>

        <div className="space-y-3">
          <Panel title="Network state" subtitle="all values SIMULATED">
            {data ? (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <Stat
                    label="Transformer loading"
                    value={pct(data.state.transformer_loading_pct)}
                    tone={
                      data.state.transformer_loading_pct >= 100
                        ? 'text-status-critical'
                        : data.state.transformer_loading_pct >= 85
                          ? 'text-status-warning'
                          : 'text-status-normal'
                    }
                  />
                  <Stat label="Total load" value={`${num(data.state.total_load_kw)} kW`} />
                  <Stat label="LV bus voltage" value={`${num(data.state.lv_bus_voltage_pu, 4)} pu`} />
                  <Stat label="Min bus voltage" value={`${num(data.state.min_bus_voltage_pu, 4)} pu`} />
                  <Stat label="Network losses" value={`${num(data.state.losses_kw, 2)} kW`} />
                  <Stat label="Capacity (calibrated)" value={`${num(data.cap_kw)} kW`} />
                </div>
                <div className="mt-2.5">
                  <NetworkViolations violations={data.state.violations} />
                </div>
                <div className="mt-2.5 border-t border-base-700 pt-2.5">
                  <h4 className="text-[10px] uppercase tracking-wider text-ink-500">Assumptions</h4>
                  <ul className="mt-1 space-y-1">
                    {data.state.assumptions.map((assumption) => (
                      <li key={assumption} className="flex gap-1.5 text-[10px] leading-relaxed text-ink-400">
                        <span className="text-status-warning">·</span>
                        <span>{assumption}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            ) : (
              <Skeleton className="h-64" />
            )}
          </Panel>

          {riskData && (
            <Panel
              title="Transformer risk"
              subtitle={`${riskData.horizon_minutes / 60} h forward horizon`}
              actions={
                <Pill
                  tone={
                    riskData.severity === 'CRITICAL'
                      ? 'critical'
                      : riskData.severity === 'HIGH' || riskData.severity === 'MEDIUM'
                        ? 'warning'
                        : 'neutral'
                  }
                >
                  {riskData.risk_level}
                </Pill>
              }
            >
              <div className="grid grid-cols-2 gap-2">
                <Stat label="Predicted peak" value={`${num(riskData.predicted_peak_kw)} kW`} />
                <Stat
                  label="At"
                  value={fullTimestamp(riskData.predicted_peak_at)}
                  mono
                />
                <Stat
                  label="Peak loading"
                  value={pct(riskData.predicted_peak_loading_pct)}
                  tone={
                    riskData.predicted_peak_loading_pct >= 100
                      ? 'text-status-critical'
                      : 'text-ink-100'
                  }
                />
                <Stat label="Capacity" value={`${num(riskData.cap_kw)} kW`} />
              </div>

              <div className="mt-2.5 border-t border-base-700 pt-2.5">
                <h4 className="text-[10px] uppercase tracking-wider text-ink-500">
                  Contributors at the peak
                </h4>
                <ul className="mt-1 space-y-1">
                  {riskData.contributors.map((contributor) => (
                    <li key={contributor.feeder} className="flex items-center gap-2">
                      <span className="w-24 shrink-0 truncate text-2xs text-ink-300">
                        {contributor.feeder.replace('_', ' ')}
                      </span>
                      <div className="h-1 flex-1 overflow-hidden rounded-full bg-base-600">
                        <div
                          className={cn(
                            'h-full',
                            contributor.flexible ? 'bg-accent' : 'bg-status-info',
                          )}
                          style={{ width: `${contributor.share_pct}%` }}
                        />
                      </div>
                      <span className="tabular w-20 shrink-0 text-right font-mono text-2xs text-ink-100">
                        {num(contributor.kw)} kW
                      </span>
                      {contributor.flexible && <Pill tone="accent">flex</Pill>}
                    </li>
                  ))}
                </ul>
              </div>
            </Panel>
          )}
        </div>
      </div>

      {riskData && (
        <Panel
          title="Forward demand against transformer capacity"
          actions={<ProvenanceBadge provenance={riskData.provenance.forecast} size="xs" />}
          bodyClassName="p-2"
        >
          <TimeSeriesChart
            configs={riskConfigs}
            height={220}
            yAxisName="kW"
            markLineValue={riskData.cap_kw}
            markLineLabel={`${num(riskData.cap_kw, 0)} kW = 100% transformer loading`}
          />
        </Panel>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  mono,
}: {
  label: string;
  value: string;
  tone?: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-ink-500">{label}</div>
      <div
        className={cn(
          'tabular truncate text-sm font-semibold',
          mono && 'font-mono text-xs',
          tone ?? 'text-ink-100',
        )}
      >
        {value}
      </div>
    </div>
  );
}
