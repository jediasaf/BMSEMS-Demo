'use client';

import { useEffect } from 'react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useDemo } from '@/lib/store';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { BeforeAfterPanel, type ComparisonRow } from '@/components/BeforeAfterPanel';
import { ProvenanceBadge } from '@/components/ProvenanceBadge';
import { ErrorNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { num } from '@/lib/format';
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

export default function ControlLabPage() {
  const { siteId, setSiteId, bmsScenario } = useDemo();
  const sites = useAsync(() => api.bms.sites(), []);
  useEffect(() => {
    if (sites.data && !siteId) setSiteId(sites.data.default_site_id);
  }, [sites.data, siteId, setSiteId]);

  const lab = useAsync(
    () =>
      siteId
        ? api.bms.controlLab(siteId, 24, bmsScenario)
        : Promise.reject(new Error('no site selected')),
    [siteId, bmsScenario],
  );
  const result = lab.data;

  if (lab.error) return <ErrorNote message={lab.error} onRetry={lab.reload} />;
  if (!result) return <Skeleton className="h-[30rem]" />;

  const provenance = SIM_PROVENANCE(result.engine_label, result.is_boptest);
  const optimisedProvenance: Provenance = {
    ...provenance,
    source_type: 'OPTIMISED',
    source_key: 'cvxpy',
    source_name: 'EcoTwin convex optimiser',
    publisher: 'EcoTwin AI (CVXPY)',
  };

  const tempConfigs: ChartSeriesConfig[] = [
    {
      series: toSeries('t_base', 'Zone temperature — baseline', result.timestamps, result.baseline.zone_temp_c, provenance, '°C'),
      colour: '#94a3b8',
      width: 1.5,
    },
    {
      series: toSeries('t_ai', 'Zone temperature — AI control', result.timestamps, result.ai_control.zone_temp_c, provenance, '°C'),
      colour: '#a78bfa',
      width: 1.8,
    },
    {
      series: toSeries('sp_base', 'Setpoint — baseline', result.timestamps, result.baseline.setpoint_c, provenance, '°C'),
      colour: '#4c5768',
      width: 1.1,
      dashed: true,
    },
    {
      series: toSeries('sp_ai', 'Setpoint — AI control', result.timestamps, result.ai_control.setpoint_c, optimisedProvenance, '°C'),
      colour: '#00e08a',
      width: 1.4,
      dashed: true,
    },
    {
      series: toSeries('outdoor', 'Outdoor air', result.timestamps, result.outdoor_temp_c, {
        ...provenance,
        source_type: 'MEASURED',
        source_key: 'power_laws_weather',
        source_name: 'Power Laws weather observations',
        publisher: 'Schneider Electric / DrivenData (public competition data)',
        engine: null,
        engine_label: null,
      }, '°C'),
      colour: '#3b9dfb',
      width: 1,
      opacity: 0.6,
    },
  ];

  const powerConfigs: ChartSeriesConfig[] = [
    {
      series: toSeries('p_base', 'HVAC power — baseline', result.timestamps, result.baseline.hvac_kw, provenance, 'kW'),
      colour: '#94a3b8',
      width: 1.5,
      area: true,
    },
    {
      series: toSeries('p_ai', 'HVAC power — AI control', result.timestamps, result.ai_control.hvac_kw, provenance, 'kW'),
      colour: '#00e08a',
      width: 1.8,
      area: true,
    },
  ];

  const rows: ComparisonRow[] = [
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
  ];

  const params = result.parameters as Record<string, number | string | Record<string, number>>;

  return (
    <div className="space-y-3">
      <Panel
        title="Control Lab — HVAC setpoint optimisation"
        subtitle={`asset ${result.asset_id} · zone ${result.zone_id}`}
        actions={
          <div className="flex items-center gap-1.5">
            <Pill tone={result.is_boptest ? 'accent' : 'violet'}>
              engine: {result.engine_label}
            </Pill>
            <ProvenanceBadge provenance={result.provenance} size="xs" />
          </div>
        }
        bodyClassName="space-y-2"
      >
        <p className="text-2xs leading-relaxed text-ink-300">{result.comparison_note}</p>
        {!result.is_boptest && (
          <p className="rounded-panel border border-prov-simulated/30 bg-prov-simulated/[0.06] px-2.5 py-1.5 text-2xs leading-relaxed text-ink-300">
            BOPTEST is not reachable from this deployment, so the building physics come from the
            EcoTwin RC engine — a 2R2C zone model with an ideal-load plant and a
            temperature-dependent COP. Results are labelled with the engine that produced them and
            are never presented as BOPTEST output. Local Docker mode runs BOPTEST live.
          </p>
        )}
      </Panel>

      <div className="grid gap-3 xl:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          <Panel title="Zone temperature and setpoints" bodyClassName="p-2">
            <TimeSeriesChart configs={tempConfigs} height={260} yAxisName="°C" />
          </Panel>
          <Panel title="HVAC electrical power" bodyClassName="p-2">
            <TimeSeriesChart configs={powerConfigs} height={200} yAxisName="kW" />
          </Panel>
        </div>

        <div className="space-y-3">
          <Panel title="Baseline vs AI control" subtitle="same engine, same inputs">
            <BeforeAfterPanel rows={rows} />
          </Panel>

          <Panel title="Optimisation" subtitle={result.optimisation.solver}>
            <dl className="space-y-1 text-2xs">
              <Row label="Status" value={result.optimisation.status} />
              <Row label="Solve time" value={`${num(result.optimisation.solve_time_s * 1000, 1)} ms`} />
              <Row label="Max step change" value={`${num(result.optimisation.max_step_change_k, 2)} K`} />
              <Row label="Comfort slack" value={`${num(result.optimisation.comfort_slack_kh, 4)} K·h`} />
            </dl>
            <div className="mt-2 border-t border-base-700 pt-2">
              <h4 className="text-[10px] uppercase tracking-wider text-ink-500">Constraints</h4>
              <ul className="mt-1 space-y-0.5">
                {result.optimisation.constraints.map((constraint) => (
                  <li key={constraint} className="flex gap-1.5 text-2xs text-ink-300">
                    <span className="text-accent">·</span>
                    {constraint}
                  </li>
                ))}
              </ul>
            </div>
            <div className="mt-2 border-t border-base-700 pt-2">
              {result.optimisation.notes.map((note) => (
                <p key={note} className="text-[10px] leading-relaxed text-ink-500">
                  {note}
                </p>
              ))}
            </div>
          </Panel>

          <Panel title="Model parameters" subtitle="every one of them, on purpose">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              {Object.entries(params)
                .filter(([, value]) => typeof value === 'number' || typeof value === 'string')
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2 text-[10px]">
                    <dt className="truncate text-ink-500" title={key}>
                      {key}
                    </dt>
                    <dd className="tabular shrink-0 font-mono text-ink-200">
                      {typeof value === 'number' ? num(value, value < 10 ? 2 : 0) : String(value)}
                    </dd>
                  </div>
                ))}
            </dl>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-ink-500">{label}</dt>
      <dd className="tabular font-mono text-ink-100">{value}</dd>
    </div>
  );
}
