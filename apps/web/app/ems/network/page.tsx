'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { cursorTimestamp, useDemo } from '@/lib/store';
import { Workspace } from '@/components/AppShell';
import { PageHeader } from '@/components/PageHeader';
import { NetworkDiagram, NetworkViolations } from '@/components/NetworkDiagram';
import { ReplayControl } from '@/components/ReplayControl';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { ProvenanceBadge } from '@/components/ProvenanceBadge';
import { ErrorNote, Field, Meter, Panel, Pill, Readout, Skeleton } from '@/components/Primitives';
import { DataQualityDrawer } from '@/features/bms/DataQualityDrawer';
import { cn, fullTimestamp, num, pct } from '@/lib/format';

const FEEDER_LABEL: Record<string, string> = {
  F1_HVAC: 'HVAC / chiller plant',
  F2_LIGHTING: 'Lighting and small power',
  F3_OFFICE: 'Office and IT',
  F4_FLEXIBLE: 'EV charging / flexible',
};

export default function PowerNetworkPage() {
  const {
    facilityId,
    setFacilityId,
    emsScenario,
    setEmsScenario,
    scenarios,
    window: replayWindow,
    cursor,
    resetToken,
  } = useDemo();
  const [selectedAsset, setSelectedAsset] = useState<string | null>('TR-01');
  useEffect(() => setSelectedAsset('TR-01'), [resetToken]);
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

  const data = network.data;
  const riskData = risk.data;
  const loading = data?.state.transformer_loading_pct ?? 0;
  const loadingTone = loading >= 100 ? 'critical' : loading >= 85 ? 'warning' : ('accent' as const);

  return (
    <>
      <PageHeader
        module="EMS"
        title="Power Network"
        subtitle="pandapower AC load flow"
        chips={[
          { label: 'Facility', value: data?.facility_id ?? '…' },
          { label: 'Mode', value: 'Real + simulation', tone: 'violet' },
          {
            label: 'Network',
            value: data?.state.converged ? 'Converged' : 'Not converged',
            tone: data?.state.converged ? 'accent' : 'critical',
          },
          ...(data ? [{ label: 'At', value: fullTimestamp(data.at) }] : []),
        ]}
        actions={
          <>
            <label className="flex items-center gap-1.5 text-3xs uppercase tracking-[0.08em] text-ink-500">
              Facility
              <select
                value={facilityId ?? ''}
                onChange={(event) => setFacilityId(event.target.value)}
                className="focus-ring rounded-panel border border-base-600 bg-base-800 px-1.5 py-[3px] text-2xs normal-case tracking-normal text-ink-100"
              >
                {facilities.data?.facilities.map((facility) => (
                  <option key={String(facility.facility_id)} value={String(facility.facility_id)}>
                    {String(facility.name)}
                  </option>
                ))}
              </select>
            </label>
            {facilityId && <DataQualityDrawer assetId={facilityId} module="ems" />}
          </>
        }
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

          {network.error && <ErrorNote message={network.error} onRetry={network.reload} />}

          <div className="grid items-start gap-2.5 xl:grid-cols-[1.55fr_1fr]">
            <div className="flex min-w-0 flex-col gap-2.5">
              <Panel
                title="Single line diagram"
                subtitle="click an asset for its detail"
                actions={
                  data ? <ProvenanceBadge provenance={data.provenance} size="xs" /> : undefined
                }
                flush
                bodyClassName="p-1"
              >
                {data ? (
                  <NetworkDiagram
                    network={data}
                    onSelect={setSelectedAsset}
                    selected={selectedAsset}
                  />
                ) : (
                  network.loading && <Skeleton className="m-2.5 h-[330px] w-full" />
                )}
              </Panel>

              {/* Bus / line tables */}
              {data && (
                <div className="grid gap-2.5 lg:grid-cols-2">
                  <Panel
                    title="Bus voltages"
                    subtitle="EN 50160 band 0.90 – 1.10 pu"
                    flush
                    bodyClassName="overflow-x-auto"
                  >
                    <table className="tech-table">
                      <thead>
                        <tr>
                          <th>Bus</th>
                          <th className="text-right">Voltage</th>
                          <th className="text-right">Deviation</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(data.state.bus_voltages_pu).map(([name, value]) => {
                          const ok = value >= 0.9 && value <= 1.1;
                          return (
                            <tr key={name}>
                              <td className="font-mono text-ink-200">{name}</td>
                              <td className="tabular text-right font-mono">{num(value, 4)} pu</td>
                              <td
                                className={cn(
                                  'tabular text-right font-mono',
                                  value < 1 ? 'text-status-warning' : 'text-ink-400',
                                )}
                              >
                                {num((value - 1) * 100, 2)}%
                              </td>
                              <td>
                                <Pill tone={ok ? 'neutral' : 'critical'}>
                                  {ok ? 'In band' : 'Out of band'}
                                </Pill>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </Panel>

                  <Panel title="Feeder loading" flush bodyClassName="overflow-x-auto">
                    <table className="tech-table">
                      <thead>
                        <tr>
                          <th>Feeder</th>
                          <th className="text-right">Load</th>
                          <th className="text-right">Cable</th>
                          <th>Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.topology.feeders.map((feeder) => (
                          <tr
                            key={feeder.id}
                            onClick={() => setSelectedAsset(feeder.id)}
                            className="cursor-pointer transition-colors hover:bg-base-800/70"
                          >
                            <td>
                              <div className="flex w-[11.5rem] items-baseline gap-1.5">
                                <span className="shrink-0 font-mono text-ink-200">
                                  {feeder.id.replace(/_/g, ' ')}
                                </span>
                                <span
                                  className="truncate text-3xs text-ink-600"
                                  title={feeder.label}
                                >
                                  {feeder.label}
                                </span>
                              </div>
                            </td>
                            <td className="tabular text-right font-mono text-ink-100">
                              {num(data.state.feeder_load_kw[feeder.id] ?? 0, 1)} kW
                            </td>
                            <td className="tabular text-right font-mono">
                              {pct(data.state.feeder_loading_pct[feeder.id] ?? 0, 0)}
                            </td>
                            <td>
                              <Pill tone={feeder.flexible ? 'accent' : 'neutral'}>
                                {feeder.flexible ? 'Flexible' : 'Fixed'}
                              </Pill>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Panel>
                </div>
              )}
            </div>

            {/* Transformer / feeder detail */}
            <div className="flex min-w-0 flex-col gap-2.5">
              {data && selectedAsset === 'TR-01' && riskData && (
                <Panel
                  title={`Transformer ${data.topology.transformer.id}`}
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
                  <div className="grid grid-cols-2 gap-2.5">
                    <Readout
                      label="Loading at replay instant"
                      value={pct(loading)}
                      tone={
                        loading >= 100
                          ? 'text-status-critical'
                          : loading >= 85
                            ? 'text-status-warning'
                            : 'text-status-normal'
                      }
                      size="lg"
                    />
                    <Readout
                      label={`Predicted (${riskData.horizon_minutes / 60} h)`}
                      value={pct(riskData.predicted_peak_loading_pct)}
                      tone={
                        riskData.predicted_peak_loading_pct >= 100
                          ? 'text-status-critical'
                          : 'text-ink-100'
                      }
                      size="lg"
                    />
                  </div>
                  <div className="mt-2">
                    <Meter value={loading} tone={loadingTone} />
                  </div>
                  <div className="mt-2 border-t border-base-700 pt-1.5">
                    <Field
                      label="Rated"
                      value={`${num(data.topology.transformer.kva, 0)} kVA`}
                      mono
                    />
                    <Field
                      label="Capacity (calibrated)"
                      value={`${num(data.cap_kw)} kW`}
                      mono
                      title="Solved by bisection on the load flow, not kVA × power factor"
                    />
                    <Field
                      label="Vector group"
                      value={`${data.topology.transformer.vector_group} · vk ${num(
                        data.topology.transformer.vk_percent,
                        1,
                      )}%`}
                      mono
                    />
                    <Field
                      label="LV bus voltage"
                      value={`${num(data.state.lv_bus_voltage_pu, 4)} pu`}
                      mono
                    />
                    <Field
                      label="Min bus voltage"
                      value={`${num(data.state.min_bus_voltage_pu, 4)} pu`}
                      mono
                    />
                    <Field label="Losses" value={`${num(data.state.losses_kw, 2)} kW`} mono />
                    <Field
                      label="Peak expected"
                      value={fullTimestamp(riskData.predicted_peak_at)}
                      mono
                    />
                  </div>

                  <div className="mt-2 border-t border-base-700 pt-2">
                    <div className="label mb-1.5">Main contributors at the peak</div>
                    {riskData.contributors.map((contributor) => (
                      <div key={contributor.feeder} className="flex items-center gap-2 py-[3px]">
                        <span className="w-[5.5rem] shrink-0 truncate text-2xs text-ink-400">
                          {contributor.feeder.replace(/_/g, ' ')}
                        </span>
                        <Meter
                          value={contributor.share_pct}
                          tone={contributor.flexible ? 'accent' : 'info'}
                          className="flex-1"
                        />
                        <span className="tabular w-16 shrink-0 text-right font-mono text-2xs text-ink-100">
                          {num(contributor.kw)} kW
                        </span>
                        {contributor.flexible && <Pill tone="accent">flex</Pill>}
                      </div>
                    ))}
                  </div>

                  <div className="mt-2 border-t border-base-700 pt-2">
                    <NetworkViolations violations={data.state.violations} />
                  </div>
                </Panel>
              )}

              {data && selectedAsset && selectedAsset !== 'TR-01' && (
                <Panel
                  title={`Feeder ${selectedAsset.replace(/_/g, ' ')}`}
                  subtitle={FEEDER_LABEL[selectedAsset]}
                  actions={
                    data.topology.feeders.find((f) => f.id === selectedAsset)?.flexible ? (
                      <Pill tone="accent">Flexible</Pill>
                    ) : undefined
                  }
                >
                  <Readout
                    label="Load"
                    value={num(data.state.feeder_load_kw[selectedAsset] ?? 0, 1)}
                    unit="kW"
                    size="lg"
                  />
                  <div className="mt-2 border-t border-base-700 pt-1.5">
                    <Field
                      label="Cable loading"
                      value={pct(data.state.feeder_loading_pct[selectedAsset] ?? 0, 1)}
                      mono
                    />
                    <Field
                      label="Bus voltage"
                      value={`${num(data.state.bus_voltages_pu[selectedAsset] ?? 0, 4)} pu`}
                      mono
                    />
                    {(() => {
                      const feeder = data.topology.feeders.find((f) => f.id === selectedAsset);
                      if (!feeder) return null;
                      return (
                        <>
                          <Field
                            label="Parallel runs"
                            value={num(feeder.parallel_circuits ?? 1, 0)}
                            mono
                          />
                          <Field
                            label="Design share"
                            value={pct((feeder.design_share ?? 0) * 100, 0)}
                            mono
                          />
                          <Field
                            label="Length"
                            value={`${num((feeder.cable.length_km ?? 0) * 1000, 0)} m`}
                            mono
                          />
                          <Field
                            label="R / X"
                            value={`${num(feeder.cable.r_ohm_per_km ?? 0, 3)} / ${num(
                              feeder.cable.x_ohm_per_km ?? 0,
                              3,
                            )} Ω/km`}
                            mono
                          />
                        </>
                      );
                    })()}
                  </div>
                  <p className="mt-2 border-t border-base-700 pt-1.5 text-3xs leading-relaxed text-ink-600">
                    Feeder loads are a documented disaggregation of the measured site total using an
                    HVAC sensitivity fitted to this site&apos;s own weather response. They are not
                    measured sub-meters.
                  </p>
                </Panel>
              )}

              {data && (
                <Panel title="Network state" subtitle="all values simulated">
                  <div className="grid grid-cols-2 gap-2.5">
                    <Readout
                      label="Total load"
                      value={num(data.state.total_load_kw, 1)}
                      unit="kW"
                    />
                    <Readout label="Losses" value={num(data.state.losses_kw, 2)} unit="kW" />
                  </div>
                  <div className="mt-2 border-t border-base-700 pt-1.5">
                    <div className="label mb-1">Assumptions</div>
                    <ul className="space-y-1">
                      {data.state.assumptions.map((assumption) => (
                        <li
                          key={assumption}
                          className="flex gap-1.5 text-3xs leading-relaxed text-ink-500"
                        >
                          <span className="shrink-0 text-status-warning">·</span>
                          <span>{assumption}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </Panel>
              )}

              {!data && network.loading && <Skeleton className="h-[360px]" />}
              {!data && network.error && (
                <ErrorNote message={network.error} onRetry={network.reload} />
              )}
            </div>
          </div>
        </div>
      </Workspace>
    </>
  );
}
