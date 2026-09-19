'use client';

import { ExternalLink } from 'lucide-react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { Workspace } from '@/components/AppShell';
import { PageHeader } from '@/components/PageHeader';
import { DataSourcePanel } from '@/components/DataSourcePanel';
import { ErrorNote, Panel, Pill, Skeleton } from '@/components/Primitives';
import { PROVENANCE_STYLE } from '@/lib/format';
import type { SourceType } from '@/lib/types';

const ORDER: SourceType[] = [
  'MEASURED',
  'DERIVED',
  'PREDICTED',
  'SIMULATED',
  'OPTIMISED',
  'INJECTED',
];

interface SourceRow {
  key: string;
  name: string;
  publisher: string;
  url: string | null;
  licence: string;
  description: string;
  is_real_measurement: boolean;
}

export default function AboutPage() {
  const sources = useAsync(() => api.sources(), []);
  const registry = (sources.data?.registry ?? []) as SourceRow[];

  return (
    <>
      <PageHeader
        module="BMS"
        title="About &amp; provenance"
        subtitle="What is real, what is modelled, and how they are kept apart"
        chips={[{ label: 'Build', value: 'Portfolio prototype' }]}
      />

      <Workspace>
        <div className="grid items-start gap-2.5 xl:grid-cols-[1.6fr_1fr]">
          <div className="min-w-0 space-y-2.5">
            <Panel title="Provenance vocabulary" subtitle="enforced in the backend">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {ORDER.map((type) => {
                  const style = PROVENANCE_STYLE[type];
                  return (
                    <div
                      key={type}
                      className={`rounded-panel border ${style.border} ${style.bg} px-2.5 py-2`}
                    >
                      <div className={`font-mono text-2xs font-semibold uppercase ${style.text}`}>
                        {type}
                      </div>
                      <p className="mt-1 text-3xs leading-relaxed text-ink-400">{style.blurb}</p>
                    </div>
                  );
                })}
              </div>
              <p className="mt-2.5 border-t border-base-700 pt-2.5 text-2xs leading-relaxed text-ink-500">
                Two of these are validators on the model, not conventions: a value cannot be tagged
                MEASURED unless its registered source is a real measurement, and cannot be tagged
                SIMULATED without naming the engine that produced it. A mislabelled number fails at
                construction rather than reaching a chart.
              </p>
            </Panel>

            <Panel
              title="Citable sources"
              subtitle="nothing outside this list can be cited"
              flush
              bodyClassName="overflow-x-auto"
            >
              {sources.error && (
                <div className="p-2.5">
                  <ErrorNote message={sources.error} onRetry={sources.reload} />
                </div>
              )}
              {!sources.data && <Skeleton className="m-2.5 h-48" />}
              {registry.length > 0 && (
                <table className="tech-table min-w-[42rem]">
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Publisher</th>
                      <th>Kind</th>
                      <th>Licence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {registry.map((source) => (
                      <tr key={source.key}>
                        <td>
                          <span className="text-ink-100">{source.name}</span>
                          {source.url && (
                            <a
                              href={source.url}
                              target="_blank"
                              rel="noreferrer"
                              className="focus-ring ml-1.5 inline-flex text-accent"
                              aria-label={`Open ${source.name}`}
                            >
                              <ExternalLink className="h-2.5 w-2.5" />
                            </a>
                          )}
                          <div className="mt-0.5 w-[19rem] whitespace-normal text-3xs leading-relaxed text-ink-600">
                            {source.description}
                          </div>
                        </td>
                        <td className="align-top">
                          <div className="w-[9.5rem] whitespace-normal">{source.publisher}</div>
                        </td>
                        <td className="align-top">
                          <Pill tone={source.is_real_measurement ? 'accent' : 'neutral'}>
                            {source.is_real_measurement ? 'Measurement' : 'Model'}
                          </Pill>
                        </td>
                        <td className="align-top text-3xs text-ink-500">
                          <div className="w-[11rem] whitespace-normal leading-relaxed">
                            {source.licence}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </div>

          <div className="min-w-0 space-y-2.5">
            <DataSourcePanel />

            <Panel title="What this prototype is not">
              <ul className="space-y-1.5 text-2xs leading-relaxed text-ink-400">
                <li>
                  <span className="text-ink-200">Not an official Schneider Electric product.</span>{' '}
                  EcoStruxure-ready architecture, designed for future integration with EcoStruxure
                  Building Operation and Power Monitoring Expert.
                </li>
                <li>
                  <span className="text-ink-200">
                    Not connected to a live customer environment.
                  </span>{' '}
                  Public Schneider data are used for analytics; every control experiment runs in
                  simulation.
                </li>
                <li>
                  <span className="text-ink-200">No cost or CO₂ figures anywhere.</span> Configuring
                  a tariff or an emission factor would be an invention, so neither is shown.
                </li>
                <li>
                  <span className="text-ink-200">No real actuation.</span> Historical mode is
                  read-only and there is no code path to a real actuator.
                </li>
              </ul>
            </Panel>

            <Panel title="Known limitations">
              <ul className="space-y-1.5 text-2xs leading-relaxed text-ink-400">
                <li>
                  The replay window is three days because every usable stretch of the source is a
                  contiguous 10-day block and the forecaster&apos;s lags claim five of them.
                </li>
                <li>
                  The thermal model is single-zone and calibrated against whole-site demand: the
                  source has no zone telemetry to validate it against.
                </li>
                <li>
                  Two facilities&apos; prediction intervals under-cover their nominal 80%. The model
                  card reports it rather than smoothing it over.
                </li>
                <li>Anomaly labels are heuristics, not diagnoses. The UI says so everywhere.</li>
              </ul>
            </Panel>
          </div>
        </div>
      </Workspace>
    </>
  );
}
