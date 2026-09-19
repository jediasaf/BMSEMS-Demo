'use client';

import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Building2, FlaskConical, PlayCircle, Zap } from 'lucide-react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useDemo } from '@/lib/store';
import { Workspace } from '@/components/AppShell';
import { PageHeader } from '@/components/PageHeader';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { TransitionStat } from '@/components/BeforeAfterPanel';
import { AcceptanceCriteria } from '@/components/AcceptanceCriteria';
import { ProvenanceBadge } from '@/components/ProvenanceBadge';
import { ReplayNotice } from '@/components/ReplayNotice';
import {
  Button,
  EmptyNote,
  ErrorNote,
  Field,
  Meter,
  Panel,
  Pill,
  Readout,
  Skeleton,
} from '@/components/Primitives';
import { PROVENANCE_STYLE, cn, fullTimestamp, num, pct } from '@/lib/format';
import type { CrossModuleResult, OptimiseResponse, Provenance, Series } from '@/lib/types';

export default function ScenarioLabPage() {
  const { facilityId, setFacilityId, emsScenario, setEmsScenario, scenarios, resetToken } =
    useDemo();
  const [optimisation, setOptimisation] = useState<OptimiseResponse | null>(null);
  const [optimising, setOptimising] = useState(false);
  const [optimiseError, setOptimiseError] = useState<string | null>(null);
  const [chain, setChain] = useState<CrossModuleResult | null>(null);
  const [chaining, setChaining] = useState(false);
  const [chainError, setChainError] = useState<string | null>(null);

  const facilities = useAsync(() => api.ems.facilities(), []);
  useEffect(() => {
    if (facilities.data && !facilityId) setFacilityId(facilities.data.default_facility_id);
  }, [facilities.data, facilityId, setFacilityId]);

  const risk = useAsync(
    () =>
      facilityId ? api.ems.risk(facilityId, emsScenario) : Promise.reject(new Error('no facility')),
    [facilityId, emsScenario],
  );

  // A scenario change invalidates anything computed under the previous one,
  // and so does a demo reset: an optimisation left on screen from the last
  // run is the difference between a reset and a partial reset.
  useEffect(() => {
    setOptimisation(null);
    setChain(null);
    setOptimiseError(null);
    setChainError(null);
  }, [emsScenario, facilityId, resetToken]);

  const emsScenarios = scenarios.filter((s) => s.module === 'EMS');
  const active = emsScenarios.find((s) => s.scenario_id === emsScenario);

  const runOptimisation = async () => {
    if (!facilityId) return;
    setOptimising(true);
    setOptimiseError(null);
    try {
      setOptimisation(await api.ems.optimise(facilityId, emsScenario));
    } catch (error) {
      setOptimiseError(error instanceof Error ? error.message : 'Optimisation failed');
    } finally {
      setOptimising(false);
    }
  };

  const runChain = async () => {
    if (!facilityId) return;
    setChaining(true);
    setChainError(null);
    try {
      setChain(await api.link.simulateHvacAction(facilityId, emsScenario));
    } catch (error) {
      setChainError(error instanceof Error ? error.message : 'Cross-module run failed');
    } finally {
      setChaining(false);
    }
  };

  const dispatchConfigs: ChartSeriesConfig[] = useMemo(() => {
    if (!optimisation) return [];
    const base: Provenance = optimisation.provenance.network;
    const opt: Provenance = optimisation.provenance.optimisation;
    const mk = (id: string, label: string, values: number[], prov: Provenance): Series => ({
      series_id: id,
      label,
      unit: 'kW',
      timestamps: optimisation.timestamps,
      values,
      provenance: prov,
    });
    return [
      {
        series: mk('baseline', 'Demand before dispatch', optimisation.baseline_kw, base),
        colour: '#ff5a5f',
        width: 1.6,
      },
      {
        series: mk('optimised', 'Demand after dispatch', optimisation.optimised_kw, opt),
        colour: '#3ddc97',
        width: 1.9,
      },
      {
        series: mk('ev_red', 'EV curtailment', optimisation.ev_reduction_kw, opt),
        colour: '#f472b6',
        width: 1.1,
        area: true,
      },
      {
        series: mk('ev_rec', 'EV recovery', optimisation.ev_recovery_kw, opt),
        colour: '#a98bfa',
        width: 1.1,
        area: true,
      },
      {
        series: mk('hvac_red', 'HVAC reduction', optimisation.hvac_reduction_kw, opt),
        colour: '#f2b544',
        width: 1.1,
      },
    ];
  }, [optimisation]);

  const before = risk.data?.predicted_peak_loading_pct ?? 0;
  const afterEvent = optimisation?.network_before.transformer_loading_pct ?? before;
  const afterOpt = optimisation?.network_after.transformer_loading_pct ?? null;
  // One scale for all three bars, with room above 100%: clamping each bar at
  // its own full width would draw 139% and 96% the same length, which is the
  // one comparison this panel exists to make.
  const stageScale = Math.max(110, before, afterEvent, afterOpt ?? 0) * 1.04;

  return (
    <>
      <PageHeader
        module="EMS"
        title="Scenario Lab"
        subtitle="Seeded disturbance → risk → optimisation → verification"
        chips={[
          { label: 'Facility', value: facilityId ?? '…' },
          { label: 'Mode', value: 'Real + simulation', tone: 'violet' },
          ...(risk.data
            ? [
                {
                  label: 'Risk',
                  value: risk.data.risk_level,
                  tone:
                    risk.data.severity === 'CRITICAL'
                      ? ('critical' as const)
                      : risk.data.severity === 'HIGH' || risk.data.severity === 'MEDIUM'
                        ? ('warning' as const)
                        : ('neutral' as const),
                },
              ]
            : []),
        ]}
        actions={
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
        }
      />

      <Workspace>
        <div className="space-y-2.5">
          {/* Scenario cards */}
          <div className="grid gap-2 sm:grid-cols-3">
            {emsScenarios.map((scenario) => {
              const isActive = scenario.scenario_id === emsScenario;
              return (
                <button
                  key={scenario.scenario_id}
                  type="button"
                  data-active={isActive}
                  onClick={() => setEmsScenario(scenario.scenario_id)}
                  className={cn(
                    'focus-ring rounded-panel border px-2.5 py-2 text-left transition-colors',
                    isActive
                      ? 'border-accent/55 bg-accent/[0.08]'
                      : 'border-base-600 bg-base-850/70 hover:border-base-500',
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    {!scenario.is_baseline && (
                      <FlaskConical
                        className={cn('h-3 w-3', isActive ? 'text-accent' : 'text-ink-500')}
                      />
                    )}
                    <span
                      className={cn(
                        'truncate text-2xs font-semibold uppercase tracking-[0.08em]',
                        isActive ? 'text-accent' : 'text-ink-200',
                      )}
                    >
                      {scenario.name}
                    </span>
                    {scenario.is_baseline && <Pill tone="neutral">Reference</Pill>}
                  </div>
                  <p className="mt-1 line-clamp-2 text-3xs leading-relaxed text-ink-500">
                    {scenario.subtitle}
                  </p>
                </button>
              );
            })}
          </div>

          {/* Scenario detail + action strip */}
          {active && (
            <Panel title={active.name} subtitle={active.subtitle}>
              <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
                <div>
                  <p className="text-2xs leading-relaxed text-ink-300">{active.description}</p>
                  <p className="mt-1.5 border-t border-base-700 pt-1.5 text-2xs leading-relaxed text-ink-500">
                    <span className="text-ink-600">What it demonstrates — </span>
                    {active.teaches}
                  </p>
                  {Object.keys(active.parameters).length > 0 && (
                    <dl className="mt-1.5 flex flex-wrap gap-x-5 gap-y-0.5 border-t border-base-700 pt-1.5">
                      {Object.entries(active.parameters).map(([key, value]) => (
                        <div key={key} className="flex gap-1.5 text-3xs">
                          <dt className="text-ink-600">{key.replace(/_/g, ' ')}</dt>
                          <dd className="tabular font-mono text-ink-200">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>

                {/* Before / after event / after optimisation */}
                <div className="rounded-panel border border-base-600 bg-base-800/60 p-2.5">
                  <div className="label mb-2">Transformer loading</div>
                  <div className="space-y-2">
                    <Stage
                      label="Forecast peak"
                      value={before}
                      scaleMax={stageScale}
                      tone={before >= 100 ? 'critical' : before >= 85 ? 'warning' : 'accent'}
                    />
                    {optimisation && (
                      <>
                        <Stage
                          label="At the worst instant"
                          value={afterEvent}
                          scaleMax={stageScale}
                          tone={
                            afterEvent >= 100 ? 'critical' : afterEvent >= 85 ? 'warning' : 'accent'
                          }
                        />
                        {afterOpt !== null && (
                          <Stage
                            label="After optimisation"
                            value={afterOpt}
                            scaleMax={stageScale}
                            tone={
                              afterOpt >= 100 ? 'critical' : afterOpt >= 85 ? 'warning' : 'accent'
                            }
                            highlight
                          />
                        )}
                      </>
                    )}
                  </div>
                  <p className="mt-1.5 text-3xs text-ink-600">
                    The tick on each bar is 100% loading; bars run past it on purpose.
                  </p>
                  <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-base-700 pt-2">
                    <Button variant="primary" onClick={runOptimisation} disabled={optimising}>
                      <PlayCircle className="h-3 w-3" />
                      {optimising ? 'Optimising…' : 'Run optimisation'}
                    </Button>
                    <Button onClick={runChain} disabled={chaining}>
                      <Building2 className="h-3 w-3" />
                      {chaining ? 'Simulating…' : 'Open BMS analysis'}
                    </Button>
                  </div>
                </div>
              </div>
            </Panel>
          )}

          {risk.error && <ErrorNote message={risk.error} onRetry={risk.reload} />}
          {optimisation?.served_from === 'demo_cache' && (
            <ReplayNotice note={optimisation.replay_note} recordedAt={optimisation.recorded_at} />
          )}
          {optimiseError && <ErrorNote message={optimiseError} onRetry={runOptimisation} />}
          {!risk.data && risk.loading && <Skeleton className="h-40" />}

          {optimisation && (
            <div className="grid gap-2.5 xl:grid-cols-[1.6fr_1fr]">
              <Panel
                title="Flexible-load dispatch"
                subtitle={`${optimisation.summary.solver} · ${num(
                  optimisation.summary.solve_time_s * 1000,
                  1,
                )} ms`}
                actions={
                  <ProvenanceBadge provenance={optimisation.provenance.optimisation} size="xs" />
                }
                flush
              >
                <TimeSeriesChart
                  configs={dispatchConfigs}
                  height={300}
                  yAxisName="kW"
                  markLineValue={optimisation.summary.cap_kw}
                  markLineLabel={`${num(optimisation.summary.cap_kw, 0)} kW capacity`}
                />
              </Panel>

              <div className="flex min-w-0 flex-col gap-2.5">
                <Panel title="Result">
                  <div className="grid grid-cols-2 gap-2.5">
                    <Readout
                      label="Peak before"
                      value={num(optimisation.summary.baseline_peak_kw)}
                      unit="kW"
                      tone="text-status-critical"
                    />
                    <Readout
                      label="Peak after"
                      value={num(optimisation.summary.optimised_peak_kw)}
                      unit="kW"
                      tone="text-accent"
                    />
                  </div>
                  <div className="mt-2 border-t border-base-700 pt-1.5">
                    <Field
                      label="Peak reduction"
                      value={`${num(optimisation.summary.peak_reduction_kw)} kW`}
                      mono
                    />
                    <Field
                      label="Target"
                      value={`${num(optimisation.summary.target_kw)} kW`}
                      mono
                    />
                    <Field
                      label="EV energy shifted"
                      value={`${num(optimisation.summary.ev_energy_shifted_kwh)} kWh`}
                      mono
                    />
                    <Field
                      label="HVAC energy given up"
                      value={`${num(optimisation.summary.hvac_energy_kwh)} kWh`}
                      mono
                    />
                  </div>
                  <div className="mt-2 border-t border-base-700 pt-2">
                    <Pill tone={optimisation.summary.feasible_within_cap ? 'accent' : 'critical'}>
                      {optimisation.summary.feasible_within_cap
                        ? 'Constraint satisfied'
                        : `${num(optimisation.summary.residual_overload_kw)} kW overload remains`}
                    </Pill>
                    <ul className="mt-1.5 space-y-0.5">
                      {optimisation.constraints.map((constraint) => (
                        <li
                          key={constraint}
                          className="flex gap-1.5 text-3xs leading-relaxed text-ink-500"
                        >
                          <span className="shrink-0 text-accent">·</span>
                          {constraint}
                        </li>
                      ))}
                    </ul>
                  </div>
                </Panel>

                <Panel
                  title="Verified by load flow"
                  subtitle={fullTimestamp(optimisation.worst_instant)}
                  actions={
                    <ProvenanceBadge provenance={optimisation.provenance.network} size="xs" />
                  }
                  bodyClassName="space-y-2"
                >
                  <TransitionStat
                    label="Transformer loading"
                    before={optimisation.network_before.transformer_loading_pct ?? 0}
                    after={optimisation.network_after.transformer_loading_pct ?? 0}
                    unit="%"
                    criticalAbove={100}
                    testId="loading"
                  />
                  <TransitionStat
                    label="LV bus voltage"
                    before={optimisation.network_before.lv_bus_voltage_pu ?? 0}
                    after={optimisation.network_after.lv_bus_voltage_pu ?? 0}
                    unit="pu"
                    digits={4}
                  />
                  <TransitionStat
                    label="Network losses"
                    before={optimisation.network_before.losses_kw ?? 0}
                    after={optimisation.network_after.losses_kw ?? 0}
                    unit="kW"
                    digits={2}
                  />
                  <p className="border-t border-base-700 pt-1.5 text-3xs leading-relaxed text-ink-600">
                    {optimisation.verification_note}
                  </p>
                </Panel>

                {optimisation.acceptance && (
                  <Panel
                    title="Network verdict"
                    subtitle={
                      optimisation.acceptance.accepted ? 'dispatch accepted' : 'dispatch rejected'
                    }
                    actions={
                      <Pill tone={optimisation.acceptance.accepted ? 'accent' : 'critical'}>
                        {optimisation.acceptance.verdict}
                      </Pill>
                    }
                  >
                    <AcceptanceCriteria verdict={optimisation.acceptance} />
                  </Panel>
                )}
              </div>
            </div>
          )}

          {chainError && <ErrorNote message={chainError} onRetry={runChain} />}

          {chain?.available && (
            <Panel
              title="BMS ↔ EMS — power risk to building action and back"
              subtitle="every link is a real computation"
              bodyClassName="space-y-2.5"
            >
              <ol className="grid gap-1.5 lg:grid-cols-5">
                {chain.chain.map((step, index) => {
                  const style = PROVENANCE_STYLE[step.source_type];
                  return (
                    <li
                      key={step.step}
                      className={cn(
                        'relative rounded-panel border bg-base-800/60 px-2.5 py-2',
                        style.border,
                      )}
                    >
                      <div className="flex items-center gap-1.5">
                        {step.module === 'EMS' ? (
                          <Zap className="h-3 w-3 text-info" />
                        ) : (
                          <Building2 className="h-3 w-3 text-accent" />
                        )}
                        <span className="label">
                          {index + 1}. {step.module}
                        </span>
                      </div>
                      <div className="mt-1 text-2xs font-semibold text-ink-100">{step.step}</div>
                      <p className="mt-1 text-3xs leading-relaxed text-ink-500">{step.detail}</p>
                      <span className={cn('mt-1.5 inline-block font-mono text-3xs', style.text)}>
                        {step.source_type}
                      </span>
                      {index < chain.chain.length - 1 && (
                        <ArrowRight className="absolute -right-2 top-1/2 hidden h-3 w-3 -translate-y-1/2 text-base-500 lg:block" />
                      )}
                    </li>
                  );
                })}
              </ol>

              <div className="grid gap-2.5 lg:grid-cols-3">
                <div className="rounded-panel border border-base-600 bg-base-800/50 p-2.5">
                  <div className="label mb-1.5">Building simulation</div>
                  <Field label="Engine" value={chain.building.engine_label} mono />
                  <Field
                    label="HVAC energy"
                    value={`${num(chain.building.baseline_kpis.energy_kwh)} → ${num(
                      chain.building.ai_kpis.energy_kwh,
                    )} kWh`}
                    mono
                  />
                  <Field
                    label="Comfort violation"
                    value={`${num(chain.building.baseline_kpis.comfort_violation_kh, 3)} → ${num(
                      chain.building.ai_kpis.comfort_violation_kh,
                      3,
                    )} K·h`}
                    mono
                  />
                </div>

                <div className="rounded-panel border border-base-600 bg-base-800/50 p-2.5">
                  <div className="label mb-1.5">HVAC reduction handed to EMS</div>
                  <Field
                    label="At the risk instant"
                    value={`${num(chain.hvac_reduction.at_peak_kw, 2)} kW`}
                    mono
                  />
                  <Field
                    label="Peak over the day"
                    value={`${num(chain.hvac_reduction.peak_reduction_kw, 2)} kW`}
                    mono
                  />
                  <Field
                    label="Energy"
                    value={`${num(chain.hvac_reduction.energy_kwh, 1)} kWh`}
                    mono
                  />
                  <div className="mt-1.5">
                    <ProvenanceBadge provenance={chain.hvac_reduction.provenance} size="xs" />
                  </div>
                </div>

                <div className="rounded-panel border border-base-600 bg-base-800/50 p-2.5">
                  <div className="label mb-1.5">Power impact, re-solved</div>
                  <TransitionStat
                    label="Transformer loading"
                    before={chain.power_impact.before.transformer_loading_pct ?? 0}
                    after={chain.power_impact.after.transformer_loading_pct ?? 0}
                    unit="%"
                    criticalAbove={100}
                  />
                  <div className="mt-1.5">
                    <ProvenanceBadge provenance={chain.power_impact.provenance} size="xs" />
                  </div>
                </div>
              </div>
            </Panel>
          )}

          {chain && !chain.available && (
            <Panel title="BMS ↔ EMS">
              <EmptyNote title="Cross-module analysis unavailable" detail={chain.reason} />
            </Panel>
          )}
        </div>
      </Workspace>
    </>
  );
}

function Stage({
  label,
  value,
  scaleMax,
  tone,
  highlight,
}: {
  label: string;
  value: number;
  /** Shared across the three stages so their bars are comparable. */
  scaleMax: number;
  tone: 'accent' | 'warning' | 'critical';
  highlight?: boolean;
}) {
  const text = {
    accent: 'text-accent',
    warning: 'text-status-warning',
    critical: 'text-status-critical',
  }[tone];
  return (
    <div className={cn(highlight && 'rounded-panel bg-accent/[0.06] px-1.5 py-1')}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-2xs text-ink-400">{label}</span>
        <span className={cn('tabular shrink-0 text-base font-semibold', text)}>
          {pct(value, 1)}
        </span>
      </div>
      <Meter value={value} max={scaleMax} mark={100} tone={tone} className="mt-1" />
    </div>
  );
}
