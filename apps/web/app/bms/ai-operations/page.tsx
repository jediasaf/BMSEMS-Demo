'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { useDemo } from '@/lib/store';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { InsightCard } from '@/components/InsightCard';
import { RecommendationCard } from '@/components/RecommendationCard';
import { TimeSeriesChart, type ChartSeriesConfig } from '@/components/TimeSeriesChart';
import { EmptyNote, ErrorNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { ModelExplanationDrawer } from '@/features/bms/ModelExplanationDrawer';
import { SEVERITY_STYLE, num } from '@/lib/format';

export default function AiOperationsPage() {
  const router = useRouter();
  const { siteId, setSiteId, bmsScenario, setBmsScenario, scenarios } = useDemo();
  const [dismissed, setDismissed] = useState<string[]>([]);

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

  const bmsScenarios = scenarios.filter((s) => s.module === 'BMS');
  const timeline = overview.data?.timeline;

  const residualConfigs: ChartSeriesConfig[] = timeline
    ? (() => {
        const byId = Object.fromEntries(timeline.series.map((s) => [s.series_id, s]));
        return byId.residual_z ? [{ series: byId.residual_z, width: 1.5, area: true }] : [];
      })()
    : [];

  const visibleRecommendations = (recommendations.data ?? []).filter(
    (recommendation) => !dismissed.includes(recommendation.recommendation_id),
  );

  return (
    <div className="space-y-3">
      <Panel
        title="Operational intelligence feed"
        subtitle={overview.data ? overview.data.site.name : undefined}
        actions={siteId ? <ModelExplanationDrawer siteId={siteId} /> : undefined}
        bodyClassName="space-y-2.5"
      >
        <ScenarioSelector
          scenarios={bmsScenarios}
          selected={bmsScenario}
          onSelect={setBmsScenario}
          injection={overview.data?.injection}
        />
        {overview.data && (
          <div className="flex flex-wrap items-center gap-2">
            {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((severity) => {
              const count = overview.data!.counts_by_severity[severity] ?? 0;
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
              <span className="text-2xs text-ink-500" title={timeline.gate_reason}>
                expected series: {timeline.served_by === 'model' ? 'LightGBM' : 'seasonal naive'}
              </span>
            )}
          </div>
        )}
      </Panel>

      <div className="grid gap-3 xl:grid-cols-[1.25fr_1fr]">
        <div className="space-y-3">
          <Panel
            title="Residual deviation score"
            subtitle="robust z against an hour-of-day baseline"
            bodyClassName="p-2"
          >
            {timeline ? (
              <>
                <TimeSeriesChart
                  configs={residualConfigs}
                  height={180}
                  yAxisName="σ"
                  markLineValue={3.5}
                  markLineLabel="threshold ±3.5σ"
                  legend={false}
                />
                <p className="px-1 pb-1 text-[10px] leading-relaxed text-ink-500">
                  The baseline is calibrated on history ending where this window begins. A rolling
                  baseline would adapt to a fault that lasts the whole window and never flag it.
                </p>
              </>
            ) : (
              <Skeleton className="h-[180px]" />
            )}
          </Panel>

          <Panel
            title="Insights"
            subtitle={insights.data ? `${insights.data.length} findings` : undefined}
            bodyClassName="space-y-1.5"
          >
            {insights.error && <ErrorNote message={insights.error} onRetry={insights.reload} />}
            {!insights.data && insights.loading && <Skeleton className="h-40" />}
            {insights.data?.length === 0 && (
              <EmptyNote
                title="Nothing exceeded the detection threshold"
                detail="Measured demand stayed inside the model's expected envelope for this window. Inject a scenario above to see the detector respond."
              />
            )}
            {insights.data?.map((insight, index) => (
              <InsightCard
                key={insight.insight_id}
                insight={insight}
                defaultOpen={index === 0}
                onSimulate={() => router.push('/bms/control-lab')}
              />
            ))}
          </Panel>
        </div>

        <div className="space-y-3">
          {recommendations.error && (
            <ErrorNote message={recommendations.error} onRetry={recommendations.reload} />
          )}
          {!recommendations.data && recommendations.loading && <Skeleton className="h-64" />}
          {recommendations.data?.length === 0 && (
            <Panel title="AI recommendations">
              <EmptyNote
                title="No action proposed"
                detail="Recommendations are only generated from a material over-consumption finding. With none in this window there is nothing to act on — and inventing one would be worse than an empty panel."
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

          {overview.data?.calibration && (
            <Panel title="Zone model" subtitle="used by the Control Lab">
              <dl className="space-y-1 text-2xs">
                <Row
                  label="Conditioned area"
                  value={`${num(overview.data.calibration.conditioned_area_m2, 0)} m² of ${num(
                    overview.data.calibration.published_floor_area_m2,
                    0,
                  )} m²`}
                />
                <Row
                  label="τ air / τ mass"
                  value={`${num(overview.data.calibration.time_constants_hours.air, 2)} h / ${num(
                    overview.data.calibration.time_constants_hours.mass,
                    1,
                  )} h`}
                />
              </dl>
              <p className="mt-2 border-t border-base-700 pt-2 text-[10px] leading-relaxed text-ink-500">
                {overview.data.calibration.method}
              </p>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-ink-500">{label}</dt>
      <dd className="tabular text-ink-100">{value}</dd>
    </div>
  );
}
