'use client';

import { ExternalLink } from 'lucide-react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { compact, num, shortDate } from '@/lib/format';
import { ErrorNote, Field, Panel, Pill, Skeleton } from './Primitives';

/**
 * What is actually behind the screen.
 *
 * Every figure here is a real count of the real files rather than a round
 * number chosen to look impressive — that is the whole point of putting it on
 * the page next to the analytics.
 */
export function DataSourcePanel({ className }: { className?: string }) {
  const { data, error, loading, reload } = useAsync(() => api.dataset(), []);

  return (
    <Panel
      title="Data source"
      actions={
        data ? (
          <Pill tone={data.data_mode === 'REAL_DATA' ? 'accent' : 'warning'}>
            {data.data_mode === 'REAL_DATA' ? 'Real data' : 'Sample fixture'}
          </Pill>
        ) : undefined
      }
      className={className}
      bodyClassName="space-y-1"
    >
      {loading && !data && <Skeleton className="h-40" />}
      {error && <ErrorNote message={error} onRetry={reload} />}
      {data?.available && (
        <>
          <div className="pb-1.5 text-2xs leading-snug text-ink-200">{data.name}</div>
          <div className="border-t border-base-700 pt-1.5">
            <Field label="Publisher" value={data.publisher} />
            <Field label="Buildings" value={num(data.buildings, 0)} mono />
            <Field label="Facilities" value={num(data.facilities, 0)} mono />
            <Field
              label="Records"
              value={compact(data.counts.total_records)}
              mono
              title={`${num(data.counts.load_records ?? 0, 0)} load + ${num(
                data.counts.weather_records ?? 0,
                0,
              )} weather + ${num(data.counts.holiday_records ?? 0, 0)} holiday rows`}
            />
            <Field label="Interval" value={`${data.sampling_minutes} min`} mono />
            <Field
              label="Span"
              value={
                data.span.first && data.span.last
                  ? `${shortDate(data.span.first)} → ${shortDate(data.span.last)}`
                  : '—'
              }
              mono
            />
            <Field label="Models" value={num(data.models, 0)} mono />
            <Field label="Update" value={data.update_cadence} />
            <Field label="Access" value={data.access} tone="text-accent" />
          </div>
          <p className="border-t border-base-700 pt-1.5 text-3xs leading-relaxed text-ink-500">
            {data.unit_note}
          </p>
          {data.url && (
            <a
              href={data.url}
              target="_blank"
              rel="noreferrer"
              className="focus-ring inline-flex items-center gap-1 pt-1 text-2xs text-accent hover:underline"
            >
              View the published dataset
              <ExternalLink className="h-2.5 w-2.5" />
            </a>
          )}
        </>
      )}
      {data && !data.available && (
        <p className="text-2xs text-ink-400">{data.reason ?? 'Dataset information unavailable.'}</p>
      )}
    </Panel>
  );
}
