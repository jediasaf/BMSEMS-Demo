'use client';

import { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useDemo } from '@/lib/store';
import { Workspace } from '@/components/AppShell';
import { PageHeader } from '@/components/PageHeader';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { BeforeAfterPanel, type ComparisonRow } from '@/components/BeforeAfterPanel';
import { ProvenanceBadge } from '@/components/ProvenanceBadge';
import { ErrorNote, Field, Panel, Pill, Skeleton } from '@/components/Primitives';
import { cn, num } from '@/lib/format';
import type { Provenance, Series } from '@/lib/types';

const SIM_PROVENANCE = (engineLabel: string, isBoptest: boolean): Provenance => ({
  source_type: 'SIMULATED',
  source_key: isBoptest ? 'boptest' : 'ecotwin_rc',
  source_name: isBoptest ? 'BOPTEST building emulator' : 'EcoTwin RC thermal engine',
  publisher: isBoptest ? 'IBPSA Project 1' : 'EcoTwin AI',
  engine: isBoptest ? 'BOPTEST' : 'ECOTWIN_RC',
  engine_label: engineLabel,
  quality: 'GOOD',
  is_fixture: false,
  assumptions: [],
  processing: 'building simulation at 15-minute steps',
});

function toSeries(
  id: string,
  label: string,
  timestamps: string[],
  values: number[],
  provenance: Provenance,
  unit: string,
): Series {
  return { series_id: id, label, unit, timestamps, values, provenance };
}

/** The Control Lab's default horizon, restored by a demo reset. */
const DEFAULT_HORIZON_HOURS = 24;

export default function ControlLabPage() {
  const { siteId, setSiteId, bmsScenario, resetToken } = useDemo();
  const [hours, setHours] = useState(DEFAULT_HORIZON_HOURS);
  useEffect(() => setHours(DEFAULT_HORIZON_HOURS), [resetToken]);

  const sites = useAsync(() => api.bms.sites(), []);
  useEffect(() => {
    if (sites.data && !siteId) setSiteId(sites.data.default_site_id);
  }, [sites.data, siteId, setSiteId]);

  const lab = useAsync(
    () =>
      siteId
        ? api.bms.controlLab(siteId, hours, bmsScenario)
        : Promise.reject(new Error('no site selected')),
    [siteId, bmsScenario, hours],
  );
  const result = lab.data;

  const provenance = result ? SIM_PROVENANCE(result.engine_label, result.is_boptest) : null;
  const optimisedProvenance: Provenance | null = provenance
    ? {
        ...provenance,
        source_type: 'OPTIMISED',
        source_key: 'cvxpy',
        source_name: 'EcoTwin convex optimiser',
        publisher: 'EcoTwin AI (CVXPY)',
      }
    : null;

  const tempConfigs: ChartSeriesConfig[] =
    result && provenance && optimisedProvenance
      ? [
          {
            series: toSeries(
              't_base',
              'Zone temp — baseline',
              result.timestamps,
              result.baseline.zone_temp_c,
              provenance,
              '°C',
            ),
            colour: '#8ba39f',
            width: 1.4,
          },
          {
            series: toSeries(
              't_ai',
              'Zone temp — AI control',
              result.timestamps,
              result.ai_control.zone_temp_c,
              provenance,
              '°C',
            ),
            colour: '#a98bfa',
            width: 1.8,
          },
          {
            series: toSeries(
              'sp_base',
              'Setpoint — baseline',
              result.timestamps,
              result.baseline.setpoint_c,
              provenance,
              '°C',
            ),
            colour: '#4a615e',
            width: 1,
            dashed: true,
          },
          {
            series: toSeries(
              'sp_ai',
              'Setpoint — AI control',
              result.timestamps,
              result.ai_control.setpoint_c,
              optimisedProvenance,
              '°C',
            ),
            colour: '#3ddc97',
            width: 1.4,
            dashed: true,
          },
          {
            series: toSeries(
              'outdoor',
              'Outdoor air',
              result.timestamps,
              result.outdoor_temp_c,
              {
                ...provenance,
                source_type: 'MEASURED',
                source_key: 'power_laws_weather',
                source_name: 'Power Laws weather observations',
                publisher: 'Schneider Electric / DrivenData (public competition data)',
                engine: null,
                engine_label: null,
              },
              '°C',
            ),
            colour: '#4cc2ff',
            width: 1,
            opacity: 0.55,
          },
        ]
      : [];

  const powerConfigs: ChartSeriesConfig[] =
    result && provenance
      ? [
          {
            series: toSeries(
              'p_base',
              'HVAC power — baseline',
              result.timestamps,
              result.baseline.hvac_kw,
              provenance,
              'kW',
            ),
            colour: '#8ba39f',
            width: 1.4,
            area: true,
          },
          {
            series: toSeries(
              'p_ai',
              'HVAC power — AI control',
              result.timestamps,
              result.ai_control.hvac_kw,
              provenance,
              'kW',
            ),
            colour: '#3ddc97',
            width: 1.8,
            area: true,
          },
        ]
      : [];

  const rows: ComparisonRow[] = result
    ? [
        {
          key: 'energy',
          label: 'HVAC electrical energy',
          before: result.baseline.kpis.energy_kwh,
          after: result.ai_control.kpis.energy_kwh,
          unit: 'kWh',
          better: 'lower',
        },
        {
          key: 'peak',
          label: 'HVAC peak power',
          before: result.baseline.kpis.peak_kw,
          after: result.ai_control.kpis.peak_kw,
          unit: 'kW',
          digits: 2,
          better: 'lower',
        },
        {
          key: 'comfort',
          label: 'Comfort violation',
          before: result.baseline.kpis.comfort_violation_kh,
          after: result.ai_control.kpis.comfort_violation_kh,
          unit: 'K·h',
          digits: 3,
          better: 'lower',
          hint: 'Degree-hours outside the active comfort band.',
        },
        {
          key: 'steps',
          label: 'Intervals out of band',
          before: result.baseline.kpis.comfort_violation_steps,
          after: result.ai_control.kpis.comfort_violation_steps,
          unit: '',
          digits: 0,
          better: 'lower',
        },
        {
          key: 'temp',
          label: 'Mean zone temperature',
          before: result.baseline.kpis.mean_zone_temp_c,
          after: result.ai_control.kpis.mean_zone_temp_c,
          unit: '°C',
          digits: 2,
          better: 'neutral',
        },
        {
          key: 'cop',
          label: 'Mean plant COP',
          before: result.baseline.kpis.cop_mean,
          after: result.ai_control.kpis.cop_mean,
          unit: '',
          digits: 3,
          better: 'higher',
        },
      ]
    : [];

  const params = (result?.parameters ?? {}) as Record<string, number | string>;

  return (
    <>
      <PageHeader
        module="BMS"
        title="Control Lab"
        subtitle="HVAC setpoint optimisation"
        chips={[
          { label: 'Mode', value: 'Simulation', tone: 'violet' },
          {
            label: 'Engine',
            value: result?.engine_label ?? '…',
            tone: result?.is_boptest ? 'accent' : 'violet',
          },
          { label: 'Asset', value: result?.asset_id ?? '…' },
          { label: 'Zone', value: result?.zone_id ?? '…' },
        ]}
        actions={
          <label className="flex items-center gap-1.5 text-3xs uppercase tracking-[0.08em] text-ink-500">
            Horizon
            <select
              value={hours}
              onChange={(event) => setHours(Number(event.target.value))}
              className="focus-ring rounded-panel border border-base-600 bg-base-800 px-1.5 py-[3px] text-2xs normal-case tracking-normal text-ink-100"
            >
              {[12, 24, 36, 48].map((h) => (
                <option key={h} value={h}>
                  {h} h
                </option>
              ))}
            </select>
          </label>
        }
      />

      {/* Simulation mode banner: this page must never be mistaken for measured data. */}
      <div className="flex shrink-0 items-center gap-2 border-b border-prov-simulated/30 bg-prov-simulated/[0.06] px-3 py-1.5">
        <FlaskConical className="h-3 w-3 shrink-0 text-prov-simulated" />
        <span className="text-3xs font-semibold uppercase tracking-[0.1em] text-prov-simulated">
          Simulation mode
        </span>
        <span className="truncate text-2xs text-ink-400">
          {result?.is_boptest
            ? 'A BOPTEST instance is answering; results are tagged BOPTEST.'
            : 'BOPTEST is not reachable from this deployment, so a 2R2C zone model with an ideal-load plant runs the case. Results are labelled with the engine that produced them and never presented as BOPTEST. Local Docker mode runs BOPTEST live.'}
        </span>
        {provenance && (
          <span className="ml-auto shrink-0">
            <ProvenanceBadge provenance={provenance} size="xs" />
          </span>
        )}
      </div>

      <Workspace>
        {lab.error && <ErrorNote message={lab.error} onRetry={lab.reload} />}
        {!result && !lab.error && <Skeleton className="h-[30rem]" />}

        {result && (
          <div className="grid gap-2.5 xl:grid-cols-[0.72fr_1.7fr_1fr]">
            {/* LEFT — case settings */}
            <div className="flex min-w-0 flex-col gap-2.5">
              <Panel title="Case" subtitle="both runs share these inputs">
                <Field label="Engine" value={result.engine_label} mono />
                <Field label="Horizon" value={`${hours} h`} mono />
                <Field label="Step" value={`${params.step_minutes ?? 15} min`} mono />
                <Field label="Integrator" value={String(params.integrator ?? '—')} />
                <Field
                  label="Deadband"
                  value={`${num(Number(params.deadband_k ?? 0), 1)} K`}
                  mono
                />
                <p className="mt-1.5 border-t border-base-700 pt-1.5 text-3xs leading-relaxed text-ink-600">
                  {result.comparison_note}
                </p>
              </Panel>

              {result.calibration && (
                <Panel title="Zone calibration">
                  <Field
                    label="Conditioned"
                    value={`${num(result.calibration.conditioned_area_m2, 0)} m²`}
                    mono
                  />
                  <Field
                    label="Of published"
                    value={`${num(result.calibration.conditioned_share * 100, 0)}%`}
                    mono
                  />
                  <Field
                    label="τ air"
                    value={`${num(result.calibration.time_constants_hours.air, 2)} h`}
                    mono
                  />
                  <Field
                    label="τ mass"
                    value={`${num(result.calibration.time_constants_hours.mass, 1)} h`}
                    mono
                  />
                  <p className="mt-1.5 border-t border-base-700 pt-1.5 text-3xs leading-relaxed text-ink-600">
                    {result.calibration.method}
                  </p>
                </Panel>
              )}

              <Panel title="Optimisation" subtitle={result.optimisation.solver}>
                <Field label="Status" value={result.optimisation.status} />
                <Field
                  label="Solve time"
                  value={`${num(result.optimisation.solve_time_s * 1000, 1)} ms`}
                  mono
                />
                <Field
                  label="Max step"
                  value={`${num(result.optimisation.max_step_change_k, 2)} K`}
                  mono
                />
                <Field
                  label="Comfort slack"
                  value={`${num(result.optimisation.comfort_slack_kh, 4)} K·h`}
                  mono
                />
                <div className="mt-1.5 border-t border-base-700 pt-1.5">
                  <div className="label mb-1">Constraints</div>
                  <ul className="space-y-0.5">
                    {result.optimisation.constraints.map((constraint) => (
                      <li
                        key={constraint}
                        className="flex gap-1.5 text-3xs leading-relaxed text-ink-400"
                      >
                        <span className="shrink-0 text-accent">·</span>
                        {constraint}
                      </li>
                    ))}
                  </ul>
                </div>
              </Panel>
            </div>

            {/* CENTRE — the two runs */}
            <div className="flex min-w-0 flex-col gap-2.5">
              <Panel title="Zone temperature and setpoints" flush>
                <TimeSeriesChart configs={tempConfigs} height={250} yAxisName="°C" yScale />
              </Panel>
              <Panel title="HVAC electrical power" flush>
                <TimeSeriesChart configs={powerConfigs} height={196} yAxisName="kW" />
              </Panel>
            </div>

            {/* RIGHT — comparison */}
            <div className="flex min-w-0 flex-col gap-2.5">
              <Panel title="Baseline vs AI control" subtitle="same engine, same inputs" flush>
                <BeforeAfterPanel rows={rows} />
              </Panel>

              <Panel
                title="Simulator verdict"
                subtitle={result.acceptance.accepted ? 'proposal accepted' : 'proposal rejected'}
                actions={
                  <Pill tone={result.acceptance.accepted ? 'accent' : 'critical'}>
                    {result.acceptance.verdict}
                  </Pill>
                }
              >
                <p
                  className={cn(
                    'text-2xs leading-relaxed',
                    result.acceptance.accepted ? 'text-ink-300' : 'text-status-critical',
                  )}
                >
                  {result.acceptance.reason}
                </p>
                <ul className="mt-2 space-y-1 border-t border-base-700 pt-2">
                  {result.acceptance.criteria.map((criterion) => (
                    <li
                      key={criterion.criterion}
                      className="flex items-baseline justify-between gap-2 text-3xs"
                    >
                      <span className="flex min-w-0 items-baseline gap-1.5">
                        <span
                          className={cn(
                            'shrink-0 font-mono',
                            criterion.passed ? 'text-accent' : 'text-status-critical',
                          )}
                        >
                          {criterion.passed ? '✓' : '✗'}
                        </span>
                        <span className="text-ink-400">{criterion.criterion}</span>
                      </span>
                      <span className="tabular shrink-0 font-mono text-ink-200">
                        {criterion.detail}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 border-t border-base-700 pt-2 text-3xs leading-relaxed text-ink-600">
                  {result.acceptance.note}
                </p>
              </Panel>

              <Panel
                title="Headline"
                subtitle={result.acceptance.accepted ? undefined : 'not claimed as a saving'}
                bodyClassName="grid grid-cols-2 gap-2"
              >
                <Headline
                  label="HVAC energy"
                  value={`${num(result.delta_pct.energy_kwh ?? 0, 1)}%`}
                  tone={
                    !result.acceptance.accepted
                      ? 'text-ink-400'
                      : (result.delta_pct.energy_kwh ?? 0) < 0
                        ? 'text-accent'
                        : 'text-status-warning'
                  }
                  sub={`${num(result.delta.energy_kwh ?? 0, 1)} kWh`}
                />
                <Headline
                  label="Peak power"
                  value={`${num(result.delta_pct.peak_kw ?? 0, 1)}%`}
                  tone={
                    !result.acceptance.accepted
                      ? 'text-ink-400'
                      : (result.delta_pct.peak_kw ?? 0) < 0
                        ? 'text-accent'
                        : 'text-status-warning'
                  }
                  sub={`${num(result.delta.peak_kw ?? 0, 2)} kW`}
                />
              </Panel>

              <Panel title="Model parameters" subtitle="every one of them, on purpose">
                <dl className="grid grid-cols-2 gap-x-3">
                  {Object.entries(params)
                    .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
                    .map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-2 py-[2px] text-3xs">
                        <dt className="truncate text-ink-600" title={key}>
                          {key}
                        </dt>
                        <dd className="tabular shrink-0 font-mono text-ink-300">
                          {typeof value === 'number'
                            ? num(value, Math.abs(value) < 10 ? 2 : 0)
                            : String(value)}
                        </dd>
                      </div>
                    ))}
                </dl>
              </Panel>

              <Panel title="Notes">
                {result.optimisation.notes.map((note) => (
                  <p key={note} className="pb-1 text-3xs leading-relaxed text-ink-500">
                    {note}
                  </p>
                ))}
                <div className="flex flex-wrap gap-1.5 border-t border-base-700 pt-1.5">
                  <Pill tone="violet">Simulated</Pill>
                  <Pill tone="accent">Optimised</Pill>
                  <Pill tone="neutral">Measured weather</Pill>
                </div>
              </Panel>
            </div>
          </div>
        )}
      </Workspace>
    </>
  );
}

function Headline({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone: string;
  sub: string;
}) {
  return (
    <div className="rounded-panel border border-base-600 bg-base-800/60 px-2.5 py-2">
      <div className="label truncate">{label}</div>
      <div className={cn('tabular mt-1 text-xl font-semibold leading-none', tone)}>{value}</div>
      <div className="tabular mt-1 font-mono text-3xs text-ink-600">{sub}</div>
    </div>
  );
}
