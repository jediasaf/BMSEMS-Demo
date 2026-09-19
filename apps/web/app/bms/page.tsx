'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { cursorTimestamp, useDemo } from '@/lib/store';
import { KpiRow } from '@/components/KpiCard';
import { ReplayControl } from '@/components/ReplayControl';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { AssetTree } from '@/components/AssetTree';
import { InsightCard } from '@/components/InsightCard';
import { ErrorNote, EmptyNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { DataQualityDrawer } from '@/features/bms/DataQualityDrawer';
import { ModelExplanationDrawer } from '@/features/bms/ModelExplanationDrawer';
import { num } from '@/lib/format';

export default function BmsOverviewPage() {
  const { siteId, setSiteId, bmsScenario, setBmsScenario, scenarios, window: replayWindow, cursor } =
    useDemo();

  const sites = useAsync(() => api.bms.sites(), []);
  useEffect(() => {
    if (sites.data && !siteId) setSiteId(sites.data.default_site_id);
  }, [sites.data, siteId, setSiteId]);

  const stamp = cursorTimestamp(replayWindow, cursor);
  const overview = useAsync(
    () =>
      siteId
        ? api.bms.overview(siteId, bmsScenario, stamp ?? undefined)
        : Promise.reject(new Error('no site selected')),
    [siteId, bmsScenario, stamp],
  );
  const assets = useAsync(
    () => (siteId ? api.bms.assets(siteId, bmsScenario) : Promise.reject(new Error('no site'))),
    [siteId, bmsScenario],
  );

  const bmsScenarios = scenarios.filter((s) => s.module === 'BMS');
  const data = overview.data;

  const chartConfigs: ChartSeriesConfig[] = data
    ? (() => {
        const byId = Object.fromEntries(data.timeline.series.map((s) => [s.series_id, s]));
        const configs: ChartSeriesConfig[] = [];
        if (byId.expected)
          configs.push({ series: byId.expected, showBand: true, dashed: true, width: 1.4 });
        if (byId.actual) configs.push({ series: byId.actual, width: 1.8, area: true });
        if (byId.outdoor_temp)
          configs.push({ series: byId.outdoor_temp, yAxisIndex: 1, width: 1.1, opacity: 0.65 });
        return configs;
      })()
    : [];

  return (
    <div className="space-y-3">
      <Panel
        title="Historical replay"
        subtitle={data ? `${data.site.name} · ${num(data.site.surface_m2, 0)} m²` : undefined}
        actions={
          <div className="flex items-center gap-1.5">
            {siteId && <ModelExplanationDrawer siteId={siteId} />}
            {siteId && <DataQualityDrawer assetId={siteId} module="bms" />}
          </div>
        }
        bodyClassName="space-y-2.5"
      >
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-2xs text-ink-400">
            Building
            <select
              value={siteId ?? ''}
              onChange={(event) => setSiteId(event.target.value)}
              className="focus-ring rounded-panel border border-base-500 bg-base-700 px-1.5 py-1 text-2xs text-ink-100"
            >
              {sites.data?.sites.map((site) => (
                <option key={String(site.site_id)} value={String(site.site_id)}>
                  {String(site.name)}
                </option>
              ))}
            </select>
          </label>
          {data?.timeline && (
            <Pill tone={data.timeline.served_by === 'model' ? 'accent' : 'warning'} title={data.timeline.gate_reason}>
              expected: {data.timeline.served_by === 'model' ? 'LightGBM' : 'seasonal naive'}
            </Pill>
          )}
          <div className="ml-auto min-w-[20rem] flex-1">
            <ReplayControl />
          </div>
        </div>
        <ScenarioSelector
          scenarios={bmsScenarios}
          selected={bmsScenario}
          onSelect={setBmsScenario}
          injection={data?.injection}
        />
      </Panel>

      {overview.error && <ErrorNote message={overview.error} onRetry={overview.reload} />}
      {!data && overview.loading && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-[5.5rem]" />
          ))}
        </div>
      )}
      {data && <KpiRow kpis={data.kpis} />}

      <div className="grid items-start gap-3 xl:grid-cols-[2fr_1fr]">
        <Panel
          title="Building load"
          subtitle="measured · expected · outdoor air"
          bodyClassName="p-2"
        >
          {data ? (
            <TimeSeriesChart
              configs={chartConfigs}
              height={320}
              yAxisName="kW"
              y2AxisName="°C"
              cursorTime={stamp ?? undefined}
            />
          ) : (
            <Skeleton className="h-[320px]" />
          )}
        </Panel>

        <div className="space-y-3">
          <Panel
            title="Recent AI insights"
            subtitle={data ? `${data.insights.length} in window` : undefined}
            actions={
              <Link
                href="/bms/ai-operations"
                className="focus-ring text-2xs text-accent hover:underline"
              >
                AI Operations →
              </Link>
            }
            bodyClassName="space-y-1.5 max-h-[22rem] overflow-y-auto"
          >
            {!data && <Skeleton className="h-32" />}
            {data && data.insights.length === 0 && (
              <EmptyNote
                title="No anomalies in this window"
                detail="The building is operating within the model's expected envelope. Switch to a scenario to inject a disturbance."
              />
            )}
            {data?.insights.map((insight) => (
              <InsightCard key={insight.insight_id} insight={insight} />
            ))}
          </Panel>

          <Panel
            title="Asset hierarchy"
            subtitle="building → floor → zone → equipment → point"
            bodyClassName="max-h-[24rem] overflow-y-auto"
          >
            {assets.data ? (
              <>
                <AssetTree root={assets.data.root} />
                <p className="mt-2 border-t border-base-700 pt-2 text-[10px] leading-relaxed text-ink-500">
                  Only the building node is backed by a measurement. This source publishes no zone
                  topology, so the hierarchy below it is generated from the published floor area
                  and every synthesised node is tagged DERIVED or SIMULATED.
                </p>
              </>
            ) : (
              <Skeleton className="h-40" />
            )}
          </Panel>
        </div>
      </div>

      {data?.calibration && (
        <Panel title="Thermal model calibration" bodyClassName="flex flex-wrap gap-6">
          <Cal label="Published floor area" value={`${num(data.calibration.published_floor_area_m2, 0)} m²`} />
          <Cal label="Conditioned area" value={`${num(data.calibration.conditioned_area_m2, 0)} m²`} />
          <Cal label="Share" value={`${num(data.calibration.conditioned_share * 100, 0)}%`} />
          <Cal label="τ air" value={`${num(data.calibration.time_constants_hours.air, 2)} h`} />
          <Cal label="τ mass" value={`${num(data.calibration.time_constants_hours.mass, 1)} h`} />
          <p className="min-w-[18rem] flex-1 text-[10px] leading-relaxed text-ink-500">
            {data.calibration.method}
          </p>
        </Panel>
      )}
    </div>
  );
}

function Cal({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-500">{label}</div>
      <div className="tabular text-sm font-semibold text-ink-100">{value}</div>
    </div>
  );
}
