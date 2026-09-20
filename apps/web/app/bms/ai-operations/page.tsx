'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useDemo } from '@/lib/store';
import { Workspace } from '@/components/AppShell';
import { PageHeader } from '@/components/PageHeader';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { InsightDetail, InsightRow } from '@/components/InsightCard';
import { RecommendationCard } from '@/components/RecommendationCard';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { EmptyNote, ErrorNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { ModelExplanationDrawer } from '@/features/bms/ModelExplanationDrawer';
import { SEVERITY_STYLE, plural } from '@/lib/format';

/**
 * The operations centre: feed on the left, the selected finding in the middle,
 * the proposed action on the right. One screen, no navigation required to get
 * from "something is off" to "here is what to do about it".
 */
export default function AiOperationsPage() {
  const router = useRouter();
  const {
    siteId,
    setSiteId,
    bmsScenario,
    setBmsScenario,
    scenarios,
    selectedInsight,
    setSelectedInsight,
    status,
    resetToken,
  } = useDemo();
  const [dismissed, setDismissed] = useState<string[]>([]);
  useEffect(() => setDismissed([]), [resetToken]);

  const sites = useAsync(() => api.bms.sites(), []);
  useEffect(() => {
    if (sites.data && !siteId) setSiteId(sites.data.default_site_id);
  }, [sites.data, siteId, setSiteId]);

  const overview = useAsync(
    () => (siteId ? api.bms.overview(siteId, bmsScenario) : Promise.reject(new Error('no site'))),
    [siteId, bmsScenario],
  );
  const insights = useAsync(
    () => (siteId ? api.bms.insights(siteId, bmsScenario) : Promise.reject(new Error('no site'))),
    [siteId, bmsScenario],
  );
  const recommendations = useAsync(
    () =>
      siteId ? api.bms.recommendations(siteId, bmsScenario) : Promise.reject(new Error('no site')),
    [siteId, bmsScenario],
  );

  // Default the selection to the first finding, and reset it when the feed changes.
  useEffect(() => {
    const list = insights.data ?? [];
    if (list.length === 0) {
      setSelectedInsight(null);
      return;
    }
    if (!list.some((i) => i.insight_id === selectedInsight)) {
      setSelectedInsight(list[0]!.insight_id);
    }
  }, [insights.data, selectedInsight, setSelectedInsight]);

  const selected = useMemo(
    () => (insights.data ?? []).find((i) => i.insight_id === selectedInsight) ?? null,
    [insights.data, selectedInsight],
  );

  const timeline = overview.data?.timeline;
  const residualConfigs: ChartSeriesConfig[] = useMemo(() => {
    if (!timeline) return [];
    const byId = Object.fromEntries(timeline.series.map((s) => [s.series_id, s]));
    return byId.residual_z ? [{ series: byId.residual_z, width: 1.4, area: true }] : [];
  }, [timeline]);

  const visibleRecommendations = (recommendations.data ?? []).filter(
    (r) => !dismissed.includes(r.recommendation_id),
  );
  const counts = overview.data?.counts_by_severity ?? {};

  return (
    <>
      <PageHeader
        module="BMS"
        title="AI Operations"
        subtitle="Operational intelligence feed"
        chips={[
          { label: 'Asset', value: overview.data?.site.name ?? '…' },
          { label: 'Source', value: status?.data_label ?? '…' },
          {
            label: 'Detector',
            value: 'Residual · hour-of-day baseline',
            tone: 'info',
          },
        ]}
        actions={siteId ? <ModelExplanationDrawer siteId={siteId} /> : undefined}
      />

      <Workspace>
        <div className="flex h-full min-h-0 flex-col gap-2.5">
          {/* Scenario + severity strip */}
          <div className="panel flex flex-row flex-wrap items-center gap-x-4 gap-y-2 px-2.5 py-2">
            <div className="flex items-start gap-2">
              <span className="label mt-[6px] shrink-0">Scenario</span>
              <ScenarioSelector
                scenarios={scenarios.filter((s) => s.module === 'BMS')}
                selected={bmsScenario}
                onSelect={setBmsScenario}
                injection={overview.data?.injection}
              />
            </div>
            <div className="ml-auto flex items-center gap-1.5">
              {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((severity) => {
                const count = counts[severity] ?? 0;
                if (!count) return null;
                return (
                  <Pill
                    key={severity}
                    tone={
                      severity === 'CRITICAL'
                        ? 'critical'
                        : severity === 'HIGH' || severity === 'MEDIUM'
                          ? 'warning'
                          : 'neutral'
                    }
                  >
                    {count} {SEVERITY_STYLE[severity].label}
                  </Pill>
                );
              })}
              {timeline && (
                <span className="text-3xs text-ink-600" title={timeline.gate_reason}>
                  expected: {timeline.served_by === 'model' ? 'LightGBM' : 'seasonal naive'}
                </span>
              )}
            </div>
          </div>

          <div className="grid min-h-0 flex-1 gap-2.5 xl:grid-cols-[0.85fr_1.25fr_1fr]">
            {/* LEFT — chronological feed */}
            <Panel
              title="Insight feed"
              subtitle={insights.data ? plural(insights.data.length, 'finding') : undefined}
              flush
              className="min-h-[24rem]"
              bodyClassName="overflow-y-auto"
            >
              {insights.error && (
                <div className="p-2.5">
                  <ErrorNote message={insights.error} onRetry={insights.reload} />
                </div>
              )}
              {!insights.data && insights.loading && <Skeleton className="m-2.5 h-40" />}
              {insights.data?.length === 0 && (
                <div className="p-2.5">
                  <EmptyNote
                    title="Nothing exceeded the threshold"
                    detail="Nothing above the materiality floor in this window."
                  />
                </div>
              )}
              {insights.data?.map((insight) => (
                <InsightRow
                  key={insight.insight_id}
                  insight={insight}
                  active={insight.insight_id === selectedInsight}
                  onClick={() => setSelectedInsight(insight.insight_id)}
                />
              ))}
            </Panel>

            {/* CENTRE — selected finding + residual trace */}
            <div className="flex min-h-0 min-w-0 flex-col gap-2.5">
              <Panel
                title="Residual deviation"
                subtitle="robust z against an hour-of-day baseline"
                flush
              >
                {timeline ? (
                  <>
                    <TimeSeriesChart
                      configs={residualConfigs}
                      height={148}
                      yAxisName="σ"
                      markLineValue={3.5}
                      markLineLabel="threshold ±3.5σ"
                      legend={false}
                      cursorTime={selected?.timestamp}
                      yScale
                    />
                    <p className="px-2.5 pb-2 text-3xs leading-relaxed text-ink-600">
                      The baseline is calibrated on history ending where this window begins. A
                      rolling baseline would adapt to a fault lasting the whole window and never
                      flag it.
                    </p>
                  </>
                ) : overview.error ? (
                  <div className="p-2.5">
                    <ErrorNote message={overview.error} onRetry={overview.reload} />
                  </div>
                ) : (
                  <Skeleton className="m-2.5 h-[140px]" />
                )}
              </Panel>

              <Panel
                title="Selected finding"
                subtitle={selected ? selected.asset_id : undefined}
                className="min-h-0 flex-1"
                bodyClassName="overflow-y-auto"
              >
                {selected ? (
                  <InsightDetail insight={selected} />
                ) : (
                  <EmptyNote
                    title="No finding selected"
                    detail="Pick an entry from the feed to see its evidence and the checks behind it."
                  />
                )}
              </Panel>
            </div>

            {/* RIGHT — proposed action */}
            <div className="flex min-h-0 min-w-0 flex-col gap-2.5 overflow-y-auto">
              {recommendations.error && (
                <ErrorNote message={recommendations.error} onRetry={recommendations.reload} />
              )}
              {!recommendations.data && recommendations.loading && <Skeleton className="h-64" />}
              {recommendations.data?.length === 0 && (
                <Panel title="AI recommendation">
                  <EmptyNote
                    title="No operational intervention recommended"
                    detail="No action required. Recommendations follow a material finding."
                  />
                </Panel>
              )}
              {visibleRecommendations.map((recommendation) => (
                <RecommendationCard
                  key={recommendation.recommendation_id}
                  recommendation={recommendation}
                  siteId={siteId ?? ''}
                  scenarioId={bmsScenario}
                  onSimulate={() => router.push('/bms/control-lab')}
                  onDismiss={() =>
                    setDismissed((current) => [...current, recommendation.recommendation_id])
                  }
                />
              ))}
            </div>
          </div>
        </div>
      </Workspace>
    </>
  );
}
