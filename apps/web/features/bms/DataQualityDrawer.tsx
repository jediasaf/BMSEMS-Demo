'use client';

import { useState } from 'react';
import { Database, X } from 'lucide-react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { num, pct, fullTimestamp } from '@/lib/format';
import { Button, ErrorNote, Skeleton } from '@/components/Primitives';

export function DataQualityDrawer({
  assetId,
  module,
}: {
  assetId: string;
  module: 'bms' | 'ems';
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Database className="h-3 w-3" />
        Data quality
      </Button>
      {open && <Drawer assetId={assetId} module={module} onClose={() => setOpen(false)} />}
    </>
  );
}

function Drawer({
  assetId,
  module,
  onClose,
}: {
  assetId: string;
  module: 'bms' | 'ems';
  onClose: () => void;
}) {
  const { data, error, loading, reload } = useAsync(
    () => (module === 'bms' ? api.bms.dataQuality(assetId) : api.ems.dataQuality(assetId)),
    [assetId, module],
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="h-full w-full max-w-md overflow-y-auto border-l border-base-600 bg-base-850 p-4"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-base-600 pb-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-200">
            Data quality — asset {assetId}
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="focus-ring text-ink-400 hover:text-ink-100">
            <X className="h-4 w-4" />
          </button>
        </div>

        {loading && !data && <Skeleton className="mt-3 h-64 w-full" />}
        {error && <div className="mt-3"><ErrorNote message={error} onRetry={reload} /></div>}

        {data && (
          <div className="mt-3 space-y-3">
            <dl className="grid grid-cols-2 gap-2">
              <Stat label="Window" value={`${fullTimestamp(data.report.window_start)} → ${fullTimestamp(data.report.window_end)}`} wide />
              <Stat label="Samples" value={`${num(data.report.actual_samples, 0)} / ${num(data.report.expected_samples, 0)}`} />
              <Stat label="Missing" value={pct(data.report.missing_pct, 3)} />
              <Stat label="Sampling interval" value={`${num(data.report.sampling_minutes, 0)} min`} />
              <Stat label="Duplicate timestamps" value={num(data.report.duplicate_timestamps, 0)} />
              <Stat label="Outliers" value={num(data.report.outlier_count, 0)} />
              <Stat label="Flatline runs" value={num(data.report.flatline_runs, 0)} />
              <Stat label="Last timestamp" value={data.report.last_timestamp ? fullTimestamp(data.report.last_timestamp) : '—'} wide />
              <Stat label="Timezone" value={data.report.timezone} wide />
            </dl>

            <Section title="Outlier rule">
              <p className="font-mono text-[10px] text-ink-300">{data.report.outlier_rule}</p>
            </Section>

            <Section title="Units">
              <dl className="space-y-0.5">
                {Object.entries(data.report.units).map(([field, unit]) => (
                  <div key={field} className="flex justify-between text-2xs">
                    <dt className="font-mono text-ink-400">{field}</dt>
                    <dd className="text-ink-200">{unit}</dd>
                  </div>
                ))}
              </dl>
            </Section>

            {data.report.notes.length > 0 && (
              <Section title="Notes">
                <ul className="space-y-1">
                  {data.report.notes.map((note) => (
                    <li key={note} className="flex gap-1.5 text-2xs leading-relaxed text-ink-300">
                      <span className="text-ink-600">·</span>
                      <span>{note}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            <Section title="Source files">
              <ul className="space-y-0.5">
                {data.report.source_files.map((file) => (
                  <li key={file} className="font-mono text-[10px] text-ink-300">
                    {file}
                  </li>
                ))}
              </ul>
            </Section>

            <Section title="Adapter">
              <pre className="overflow-x-auto whitespace-pre-wrap break-words text-[10px] leading-relaxed text-ink-400">
                {JSON.stringify(data.source, null, 2)}
              </pre>
            </Section>
          </div>
        )}
      </aside>
    </div>
  );
}

function Stat({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? 'col-span-2' : undefined}>
      <dt className="text-[10px] uppercase tracking-wider text-ink-500">{label}</dt>
      <dd className="tabular truncate text-2xs text-ink-100" title={value}>
        {value}
      </dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-panel border border-base-600 bg-base-800/60 p-2.5">
      <h3 className="text-[10px] uppercase tracking-wider text-ink-500">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}
