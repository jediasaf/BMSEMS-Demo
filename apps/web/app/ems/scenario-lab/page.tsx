'use client';

import { useEffect, useState } from 'react';
import { ArrowRight, Building2, PlayCircle, Zap } from 'lucide-react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useDemo } from '@/lib/store';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { TransitionStat } from '@/components/BeforeAfterPanel';
import { ProvenanceBadge } from '@/components/ProvenanceBadge';
import { Button, EmptyNote, ErrorNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { PROVENANCE_STYLE, cn, fullTimestamp, num, pct } from '@/lib/format';
import type { CrossModuleResult, OptimiseResponse, Provenance, Series } from '@/lib/types';

export default function ScenarioLabPage() {
  const { facilityId, setFacilityId, emsScenario, setEmsScenario, scenarios } = useDemo();
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
    () => (facilityId ? api.ems.risk(facilityId, emsScenario) : Promise.reject(new Error('no facility'))),
    [facilityId, emsScenario],
  );

  // A scenario change invalidates any result computed under the previous one.
  useEffect(() => {
    setOptimisation(null);
    setChain(null);
    setOptimiseError(null);
    setChainError(null);
  }, [emsScenario, facilityId]);

  const emsScenarios = scenarios.filter((s) => s.module === 'EMS');

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

  const dispatchConfigs: ChartSeriesConfig[] = optimisation
    ? (() => {
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
          { series: mk('baseline', 'Demand before dispatch', optimisation.baseline_kw, base), colour: '#f4404b', width: 1.6 },
          { series: mk('optimised', 'Demand after dispatch', optimisation.optimised_kw, opt), colour: '#00e08a', width: 1.9 },
          { series: mk('ev_red', 'EV curtailment', optimisation.ev_reduction_kw, opt), colour: '#f472b6', width: 1.1, area: true },
          { series: mk('ev_rec', 'EV recovery', optimisation.ev_recovery_kw, opt), colour: '#a78bfa', width: 1.1, area: true },
          { series: mk('hvac_red', 'HVAC reduction', optimisation.hvac_reduction_kw, opt), colour: '#f5a524', width: 1.1 },
        ];
      })()
    : [];

  return (
    <div className="space-y-3">
      <Panel title="Scenario Lab" subtitle="seeded disturbance → risk → optimisation → verification" bodyClassName="space-y-2.5">
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
          <ScenarioSelector scenarios={emsScenarios} selected={emsScenario} onSelect={setEmsScenario} />
        </div>

        {risk.data && (
          <div className="flex flex-wrap items-center gap-3 rounded-panel border border-base-600 bg-base-850/60 p-2.5">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-500">
                {risk.data.transformer_id} predicted peak loading
              </div>
              <div
                className={cn(
                  'tabular text-2xl font-semibold',
                  risk.data.predicted_peak_loading_pct >= 100
                    ? 'text-status-critical'
                    : risk.data.predicted_peak_loading_pct >= 85
                      ? 'text-status-warning'
                      : 'text-status-normal',
                )}
              >
                {pct(risk.data.predicted_peak_loading_pct)}
              </div>
            </div>
            <div className="text-2xs text-ink-400">
              <div>
                {num(risk.data.predicted_peak_kw)} kW against a {num(risk.data.cap_kw)} kW capacity
              </div>
              <div className="font-mono text-[10px]">
                expected at {fullTimestamp(risk.data.predicted_peak_at)}
              </div>
            </div>
            <Pill
              tone={
                risk.data.severity === 'CRITICAL'
                  ? 'critical'
                  : risk.data.severity === 'HIGH' || risk.data.severity === 'MEDIUM'
                    ? 'warning'
                    : 'neutral'
              }
            >
              {risk.data.risk_level}
            </Pill>
            <div className="ml-auto flex flex-wrap gap-1.5">
              <Button variant="primary" onClick={runOptimisation} disabled={optimising}>
                <PlayCircle className="h-3.5 w-3.5" />
                {optimising ? 'Optimising…' : 'Run flexible-load optimisation'}
              </Button>
              <Button onClick={runChain} disabled={chaining}>
                <Building2 className="h-3.5 w-3.5" />
                {chaining ? 'Simulating…' : 'Open BMS analysis & simulate HVAC action'}
              </Button>
            </div>
          </div>
        )}
      </Panel>

      {risk.error && <ErrorNote message={risk.error} onRetry={risk.reload} />}
      {optimiseError && <ErrorNote message={optimiseError} onRetry={runOptimisation} />}

      {optimisation && (
        <>
          <div className="grid gap-3 xl:grid-cols-[1.5fr_1fr]">
            <Panel
              title="Flexible-load dispatch"
              subtitle={`${optimisation.summary.solver} · ${num(optimisation.summary.solve_time_s * 1000, 1)} ms`}
              actions={<ProvenanceBadge provenance={optimisation.provenance.optimisation} size="xs" />}
              bodyClassName="p-2"
            >
              <TimeSeriesChart
                configs={dispatchConfigs}
                height={260}
                yAxisName="kW"
                markLineValue={optimisation.summary.cap_kw}
                markLineLabel={`${num(optimisation.summary.cap_kw, 0)} kW capacity`}
              />
            </Panel>

            <div className="space-y-3">
              <Panel title="Result">
                <div className="grid grid-cols-2 gap-2">
                  <Stat label="Peak before" value={`${num(optimisation.summary.baseline_peak_kw)} kW`} tone="text-status-critical" />
                  <Stat label="Peak after" value={`${num(optimisation.summary.optimised_peak_kw)} kW`} tone="text-accent" />
                  <Stat label="Peak reduction" value={`${num(optimisation.summary.peak_reduction_kw)} kW`} />
                  <Stat label="Target" value={`${num(optimisation.summary.target_kw)} kW`} />
                  <Stat label="EV energy shifted" value={`${num(optimisation.summary.ev_energy_shifted_kwh)} kWh`} />
                  <Stat label="HVAC energy given up" value={`${num(optimisation.summary.hvac_energy_kwh)} kWh`} />
                </div>
                <div className="mt-2.5 border-t border-base-700 pt-2.5">
                  <Pill tone={optimisation.summary.feasible_within_cap ? 'accent' : 'critical'}>
                    {optimisation.summary.feasible_within_cap
                      ? 'Constraint satisfied'
                      : `${num(optimisation.summary.residual_overload_kw)} kW overload remains`}
                  </Pill>
                </div>
                <ul className="mt-2 space-y-1">
                  {optimisation.constraints.map((constraint) => (
                    <li key={constraint} className="flex gap-1.5 text-[10px] leading-relaxed text-ink-400">
                      <span className="text-accent">·</span>
                      {constraint}
                    </li>
                  ))}
                </ul>
              </Panel>

              <Panel
                title="Verified by load flow"
                subtitle={fullTimestamp(optimisation.worst_instant)}
                actions={<ProvenanceBadge provenance={optimisation.provenance.network} size="xs" />}
              >
                <div className="space-y-2">
                  <TransitionStat
                    label="Transformer loading"
                    before={optimisation.network_before.transformer_loading_pct ?? 0}
                    after={optimisation.network_after.transformer_loading_pct ?? 0}
                    unit="%"
                    criticalAbove={100}
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
                </div>
                <p className="mt-2 border-t border-base-700 pt-2 text-[10px] leading-relaxed text-ink-500">
                  {optimisation.verification_note}
                </p>
              </Panel>
            </div>
          </div>
        </>
      )}

      {chainError && <ErrorNote message={chainError} onRetry={runChain} />}

      {chain?.available && (
        <Panel
          title="BMS ↔ EMS — power risk to building action and back"
          subtitle="every link is a real computation"
          bodyClassName="space-y-3"
        >
          <ol className="grid gap-1.5 lg:grid-cols-5">
            {chain.chain.map((step, index) => {
              const style = PROVENANCE_STYLE[step.source_type];
              return (
                <li
                  key={step.step}
                  className={cn('relative rounded-panel border bg-base-850/60 p-2.5', style.border)}
                >
                  <div className="flex items-center gap-1.5">
                    {step.module === 'EMS' ? (
                      <Zap className="h-3 w-3 text-accent" />
                    ) : (
                      <Building2 className="h-3 w-3 text-teal" />
                    )}
                    <span className="text-[10px] uppercase tracking-wider text-ink-500">
                      {index + 1}. {step.module}
                    </span>
                  </div>
                  <div className="mt-1 text-2xs font-semibold text-ink-100">{step.step}</div>
                  <p className="mt-1 text-[10px] leading-relaxed text-ink-400">{step.detail}</p>
                  <span className={cn('mt-1.5 inline-block font-mono text-[9px]', style.text)}>
                    {step.source_type}
                  </span>
                  {index < chain.chain.length - 1 && (
                    <ArrowRight className="absolute -right-2.5 top-1/2 hidden h-3 w-3 -translate-y-1/2 text-base-500 lg:block" />
                  )}
                </li>
              );
            })}
          </ol>

          <div className="grid gap-3 lg:grid-cols-3">
            <div className="rounded-panel border border-base-600 bg-base-850/50 p-2.5">
              <h4 className="text-[10px] uppercase tracking-wider text-ink-500">
                Building simulation
              </h4>
              <dl className="mt-1.5 space-y-1 text-2xs">
                <Row label="Engine" value={chain.building.engine_label} />
                <Row
                  label="HVAC energy"
                  value={`${num(chain.building.baseline_kpis.energy_kwh)} → ${num(
                    chain.building.ai_kpis.energy_kwh,
                  )} kWh`}
                />
                <Row
                  label="Comfort violation"
                  value={`${num(chain.building.baseline_kpis.comfort_violation_kh, 3)} → ${num(
                    chain.building.ai_kpis.comfort_violation_kh,
                    3,
                  )} K·h`}
                />
              </dl>
            </div>

            <div className="rounded-panel border border-base-600 bg-base-850/50 p-2.5">
              <h4 className="text-[10px] uppercase tracking-wider text-ink-500">
                HVAC reduction handed to EMS
              </h4>
              <dl className="mt-1.5 space-y-1 text-2xs">
                <Row label="At the risk instant" value={`${num(chain.hvac_reduction.at_peak_kw, 2)} kW`} />
                <Row label="Peak over the day" value={`${num(chain.hvac_reduction.peak_reduction_kw, 2)} kW`} />
                <Row label="Energy" value={`${num(chain.hvac_reduction.energy_kwh, 1)} kWh`} />
              </dl>
              <div className="mt-1.5">
                <ProvenanceBadge provenance={chain.hvac_reduction.provenance} size="xs" />
              </div>
            </div>

            <div className="rounded-panel border border-base-600 bg-base-850/50 p-2.5">
              <h4 className="text-[10px] uppercase tracking-wider text-ink-500">
                Power impact, re-solved
              </h4>
              <div className="mt-1.5">
                <TransitionStat
                  label="Transformer loading"
                  before={chain.power_impact.before.transformer_loading_pct ?? 0}
                  after={chain.power_impact.after.transformer_loading_pct ?? 0}
                  unit="%"
                  criticalAbove={100}
                />
              </div>
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

      {!optimisation && !optimising && risk.data && (
        <Panel title="What this page does">
          <ol className="space-y-1.5 text-2xs leading-relaxed text-ink-400">
            <li>
              <span className="text-ink-200">1.</span> A seeded disturbance is added on top of the
              measured demand. The measurement is never overwritten.
            </li>
            <li>
              <span className="text-ink-200">2.</span> The forecast plus the injection is checked
              against a transformer capacity calibrated by bisection on the load flow.
            </li>
            <li>
              <span className="text-ink-200">3.</span> A linear program shifts EV charging — with
              total delivered energy conserved as a hard equality, not shed — and buys HVAC
              flexibility bounded by a comfort energy budget.
            </li>
            <li>
              <span className="text-ink-200">4.</span> The result is proven by two independent
              pandapower solves at the worst instant. The optimiser does not get to mark its own
              homework.
            </li>
          </ol>
        </Panel>
      )}

      {!risk.data && risk.loading && <Skeleton className="h-64" />}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-ink-500">{label}</div>
      <div className={cn('tabular truncate text-sm font-semibold', tone ?? 'text-ink-100')}>
        {value}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="shrink-0 text-ink-500">{label}</dt>
      <dd className="tabular truncate text-right text-ink-100">{value}</dd>
    </div>
  );
}
