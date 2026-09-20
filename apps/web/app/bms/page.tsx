'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { cursorTimestamp, useDemo } from '@/lib/store';
import { Workspace } from '@/components/AppShell';
import { PageHeader } from '@/components/PageHeader';
import { KpiRow } from '@/components/KpiCard';
import { ReplayControl } from '@/components/ReplayControl';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { BuildingView, AssetDrawer } from '@/components/BuildingView';
import { InsightRow } from '@/components/InsightCard';
import { RecommendationCard } from '@/components/RecommendationCard';
import { DataSourcePanel } from '@/components/DataSourcePanel';
import { EmptyNote, ErrorNote, Field, Panel, Pill, Skeleton } from '@/components/Primitives';
import { DataQualityDrawer } from '@/features/bms/DataQualityDrawer';
import { ModelExplanationDrawer } from '@/features/bms/ModelExplanationDrawer';
import { num } from '@/lib/format';
import type { AssetNode } from '@/lib/types';

export default function BmsOverviewPage() {
  const {
    siteId,
    setSiteId,
    bmsScenario,
    setBmsScenario,
    scenarios,
    window: replayWindow,
    cursor,
    status,
    resetToken,
  } = useDemo();
  const [drawerNode, setDrawerNode] = useState<AssetNode | null>(null);
  useEffect(() => setDrawerNode(null), [resetToken]);

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
    () =>
      siteId
        ? api.bms.assets(siteId, bmsScenario, stamp ?? undefined)
        : Promise.reject(new Error('no site')),
    [siteId, bmsScenario, stamp],
  );

  const data = overview.data;
  const byId = useMemo(
    () => Object.fromEntries((data?.timeline.series ?? []).map((s) => [s.series_id, s])),
    [data],
  );

  const chartConfigs: ChartSeriesConfig[] = data
    ? [
        ...(byId.expected
          ? [{ series: byId.expected, showBand: true, dashed: true, width: 1.3 }]
          : []),
        ...(byId.actual ? [{ series: byId.actual, width: 1.7 }] : []),
        ...(byId.outdoor_temp
          ? [{ series: byId.outdoor_temp, yAxisIndex: 1, width: 1, opacity: 0.6 }]
          : []),
      ]
    : [];

  const sparks = data
    ? {
        building_load: byId.actual?.values ?? [],
        expected_load: byId.expected?.values ?? [],
        occupancy_proxy: byId.occupancy_proxy?.values ?? [],
        outdoor_temp: byId.outdoor_temp?.values ?? [],
      }
    : undefined;

  const site = sites.data?.sites.find((s) => String(s.site_id) === siteId);

  return (
    <>
      <PageHeader
        module="BMS"
        title="AI Building Operator"
        subtitle="Measured → detect → predict → recommend → simulate"
        chips={[
          { label: 'Source', value: status?.data_label ?? '…' },
          // An absent answer is not a negative answer. With no status yet, the
          // chip reads "…" rather than asserting SAMPLE FIXTURE — which would
          // be the interface inventing a fact about data it has not seen.
          {
            label: 'Mode',
            value: !status
              ? '…'
              : status.data_mode === 'REAL_DATA'
                ? 'Archive 2017'
                : 'Sample fixture',
            tone: !status ? 'neutral' : status.data_mode === 'REAL_DATA' ? 'accent' : 'warning',
          },
          {
            label: 'Expected',
            value: !data
              ? '…'
              : data.timeline.served_by === 'model'
                ? 'LightGBM'
                : 'Seasonal naive',
            tone: !data ? 'neutral' : data.timeline.served_by === 'model' ? 'info' : 'warning',
            title: data?.timeline.gate_reason,
          },
          ...(site ? [{ label: 'Area', value: `${num(site.surface_m2 as number, 0)} m²` }] : []),
        ]}
        actions={
          <>
            <label className="flex items-center gap-1.5 text-3xs uppercase tracking-[0.08em] text-ink-500">
              Building
              <select
                value={siteId ?? ''}
                onChange={(event) => setSiteId(event.target.value)}
                className="focus-ring rounded-panel border border-base-600 bg-base-800 px-1.5 py-[3px] text-2xs normal-case tracking-normal text-ink-100"
              >
                {sites.data?.sites.map((s) => (
                  <option key={String(s.site_id)} value={String(s.site_id)}>
                    {String(s.name)}
                  </option>
                ))}
              </select>
            </label>
            {siteId && <ModelExplanationDrawer siteId={siteId} />}
            {siteId && <DataQualityDrawer assetId={siteId} module="bms" />}
          </>
        }
      />

      <Workspace>
        <div className="space-y-2.5">
          {/* Replay + scenario strip */}
          <div className="panel flex flex-row flex-wrap items-center gap-x-5 gap-y-2 px-2.5 py-1.5">
            <div className="flex min-w-[26rem] max-w-[40rem] flex-1 items-center gap-2.5">
              <span className="label shrink-0">Replay</span>
              <div className="min-w-0 flex-1">
                <ReplayControl />
              </div>
            </div>
            <span className="hidden h-4 w-px bg-base-600 lg:block" />
            <div className="flex min-w-0 items-center gap-2">
              <span className="label shrink-0">Scenario</span>
              <ScenarioSelector
                scenarios={scenarios.filter((s) => s.module === 'BMS')}
                selected={bmsScenario}
                onSelect={setBmsScenario}
                injection={data?.injection}
              />
            </div>
          </div>

          {/* ROW 1 — KPIs */}
          {overview.error && <ErrorNote message={overview.error} onRetry={overview.reload} />}
          {!data && overview.loading ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-[72px]" />
              ))}
            </div>
          ) : (
            data && <KpiRow kpis={data.kpis} sparks={sparks} />
          )}

          {/* ROW 2 — chart + building view */}
          <div className="grid items-start gap-2.5 xl:grid-cols-[1.9fr_1fr]">
            <Panel
              title="Building load"
              subtitle="measured · expected · outdoor air"
              flush
              className="min-h-[340px]"
            >
              {data ? (
                <TimeSeriesChart
                  configs={chartConfigs}
                  height={316}
                  yAxisName="kW"
                  y2AxisName="°C"
                  cursorTime={stamp ?? undefined}
                />
              ) : overview.error ? (
                <div className="p-2.5">
                  <ErrorNote message={overview.error} onRetry={overview.reload} />
                </div>
              ) : (
                <Skeleton className="m-2.5 h-[300px]" />
              )}
            </Panel>

            <Panel
              title="Building view"
              subtitle={assets.data ? assets.data.root.name : undefined}
              className="min-h-[340px]"
            >
              {assets.data ? (
                <BuildingView
                  root={assets.data.root}
                  onSelect={setDrawerNode}
                  selected={drawerNode?.node_id ?? null}
                />
              ) : assets.error ? (
                <ErrorNote message={assets.error} onRetry={assets.reload} />
              ) : (
                <Skeleton className="h-[280px]" />
              )}
            </Panel>
          </div>

          {/* ROW 3 — insights + recommendation + data source */}
          <div className="grid items-start gap-2.5 xl:grid-cols-[1.15fr_1.15fr_0.7fr]">
            <Panel
              title="Recent AI insights"
              subtitle={data ? `${data.insights.length} in window` : undefined}
              actions={
                <Link
                  href="/bms/ai-operations"
                  className="focus-ring text-3xs uppercase tracking-[0.08em] text-accent hover:underline"
                >
                  AI Operations →
                </Link>
              }
              flush
              className="max-h-[22rem]"
              bodyClassName="overflow-y-auto"
            >
              {!data && overview.loading && <Skeleton className="m-2.5 h-32" />}
              {!data && overview.error && (
                <div className="p-2.5">
                  <ErrorNote message={overview.error} onRetry={overview.reload} />
                </div>
              )}
              {data && data.insights.length === 0 && (
                <div className="p-2.5">
                  <EmptyNote
                    title="No anomalies in this window"
                    detail="Nothing above the materiality floor in this window."
                  />
                </div>
              )}
              {data?.insights.map((insight) => (
                <InsightRow key={insight.insight_id} insight={insight} />
              ))}
            </Panel>

            <div className="min-w-0">
              <RecommendationPanel siteId={siteId} scenarioId={bmsScenario} />
            </div>

            <div className="flex min-w-0 flex-col gap-2.5">
              <DataSourcePanel />
              {data?.calibration && (
                <Panel title="Thermal model" subtitle="used by the Control Lab">
                  <Field
                    label="Published area"
                    value={`${num(data.calibration.published_floor_area_m2, 0)} m²`}
                    mono
                  />
                  <Field
                    label="Conditioned"
                    value={`${num(data.calibration.conditioned_area_m2, 0)} m² (${num(
                      data.calibration.conditioned_share * 100,
                      0,
                    )}%)`}
                    mono
                  />
                  <Field
                    label="τ air / mass"
                    value={`${num(data.calibration.time_constants_hours.air, 2)} h / ${num(
                      data.calibration.time_constants_hours.mass,
                      1,
                    )} h`}
                    mono
                  />
                  <p className="mt-1.5 border-t border-base-700 pt-1.5 text-3xs leading-relaxed text-ink-600">
                    {data.calibration.method}
                  </p>
                </Panel>
              )}
            </div>
          </div>
        </div>
      </Workspace>

      {drawerNode && <AssetDrawer node={drawerNode} onClose={() => setDrawerNode(null)} />}
    </>
  );
}

function RecommendationPanel({
  siteId,
  scenarioId,
}: {
  siteId: string | null;
  scenarioId: string;
}) {
  const recommendations = useAsync(
    () =>
      siteId ? api.bms.recommendations(siteId, scenarioId) : Promise.reject(new Error('no site')),
    [siteId, scenarioId],
  );

  if (recommendations.error) {
    return <ErrorNote message={recommendations.error} onRetry={recommendations.reload} />;
  }
  if (!recommendations.data) {
    return recommendations.loading ? <Skeleton className="h-[22rem]" /> : null;
  }
  if (recommendations.data.length === 0) {
    return (
      <Panel title="AI recommendation">
        <EmptyNote
          title="No operational intervention recommended"
          detail="No action required. Recommendations follow a material finding."
        />
      </Panel>
    );
  }
  return (
    <div className="max-h-[22rem] overflow-y-auto">
      <RecommendationCard
        recommendation={recommendations.data[0]!}
        siteId={siteId ?? ''}
        scenarioId={scenarioId}
        compact
      />
      {recommendations.data.length > 1 && (
        <div className="mt-1.5 flex items-center gap-1.5">
          <Pill tone="neutral">{recommendations.data.length - 1} more</Pill>
          <Link
            href="/bms/ai-operations"
            className="focus-ring text-3xs uppercase tracking-[0.08em] text-accent hover:underline"
          >
            Review in AI Operations →
          </Link>
        </div>
      )}
    </div>
  );
}
