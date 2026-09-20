'use client';

import { useEffect, useState } from 'react';
import { API_BASE, API_BASE_CONFIGURED, API_BASE_ERROR, api } from '@/lib/api';
import { useDemo } from '@/lib/store';
import { cn, fullTimestamp } from '@/lib/format';
import { cursorTimestamp } from '@/lib/store';
import { StatusDot } from './Primitives';

/**
 * The thin bar above everything. It exists for one reason: at any moment an
 * operator — or an interviewer — can read where the numbers came from, whether
 * the models are serving, and which simulator is live. It never goes quiet;
 * when something degrades it says so here first.
 */
export function SystemBar() {
  const { status, setStatus, window: replayWindow, cursor, interviewMode, preload } = useDemo();

  const [unreachable, setUnreachable] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .status()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
        setUnreachable(null);
      })
      // A frontend deployed without its backend must say so. Eight identical
      // red panels and a status bar stuck on "…" is a worse answer than one
      // line naming the API it could not reach.
      .catch((error: unknown) => {
        if (!cancelled) setUnreachable(error instanceof Error ? error.message : 'unreachable');
      });
    return () => {
      cancelled = true;
    };
  }, [setStatus]);

  const stamp = cursorTimestamp(replayWindow, cursor);

  // A build with no API base and a build whose API is down are different
  // faults with different fixes, so they get different messages.
  if (!API_BASE_CONFIGURED) {
    return (
      <div className="flex h-sysbar shrink-0 items-center gap-2 border-b border-status-critical/40 bg-status-critical/[0.08] px-3 text-2xs">
        <StatusDot tone="critical" pulse />
        <span className="shrink-0 text-3xs font-semibold uppercase tracking-[0.1em] text-status-critical">
          Not configured
        </span>
        <span className="truncate text-ink-400">{API_BASE_ERROR}</span>
      </div>
    );
  }

  if (unreachable) {
    return (
      <div className="flex h-sysbar shrink-0 items-center gap-2 border-b border-status-critical/40 bg-status-critical/[0.08] px-3 text-2xs">
        <StatusDot tone="critical" pulse />
        <span className="shrink-0 text-3xs font-semibold uppercase tracking-[0.1em] text-status-critical">
          API unreachable
        </span>
        <span className="truncate text-ink-400">
          The interface is running but no backend answered at{' '}
          <span className="tabular font-mono text-ink-200">{API_BASE}</span>. Nothing on screen is
          data — no value here is a model output.
        </span>
        <span className="tabular ml-auto shrink-0 font-mono text-3xs text-ink-600">
          {unreachable}
        </span>
      </div>
    );
  }

  return (
    <div className="flex h-sysbar shrink-0 items-center gap-3 border-b border-base-600/70 bg-base-950/90 px-3 text-2xs">
      <Segment
        label="Data"
        value={status?.data_label ?? '…'}
        tone={status ? (status.data_ok ? 'normal' : 'warning') : 'idle'}
        title={status?.source_name}
      />
      <Rule />
      <Segment
        label="AI"
        value={status?.ai_label ?? '…'}
        tone={status ? (status.ai_ok ? 'normal' : 'warning') : 'idle'}
      />
      <Rule />
      <Segment
        label="Simulation"
        value={status?.simulation_label ?? '…'}
        tone={status ? (status.simulation_engine === 'BOPTEST' ? 'normal' : 'info') : 'idle'}
        title={status?.notes.join('\n')}
      />
      {stamp && (
        <>
          <Rule />
          {/* Labelled "Archive", not "Replay": the first question anyone asks is
              why the clock says 2017. It says 2017 because that is where the
              published dataset ends, and the label should answer that before
              it is asked rather than look like a stale demo. */}
          <Segment label="Archive" value={fullTimestamp(stamp)} tone="info" mono />
        </>
      )}

      <div className="ml-auto flex min-w-0 items-center gap-2.5">
        {status?.notes.length ? (
          <span
            className="hidden min-w-0 max-w-[34rem] truncate text-ink-600 xl:inline"
            title={status.notes.join('\n')}
          >
            {status.notes[0]}
          </span>
        ) : null}
        {interviewMode && (
          <span
            title={PRELOAD_TITLE[preload.state]}
            className={cn(
              'inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-pill border px-1.5 py-[1px] text-3xs font-semibold uppercase tracking-[0.1em]',
              preload.state === 'failed'
                ? 'border-status-warning/45 bg-status-warning/10 text-status-warning'
                : 'border-accent/40 bg-accent/10 text-accent',
            )}
          >
            <StatusDot
              tone={preload.state === 'failed' ? 'warning' : 'normal'}
              pulse={preload.state !== 'loading'}
            />
            Interview
            {preload.state === 'ready' && (
              <span className="tabular font-mono font-normal normal-case tracking-normal opacity-70">
                · warm {(preload.ms / 1000).toFixed(1)}s
              </span>
            )}
            {preload.state === 'loading' && (
              <span className="font-normal normal-case tracking-normal opacity-70">
                · preloading
              </span>
            )}
            {preload.state === 'failed' && (
              <span className="font-normal normal-case tracking-normal opacity-80">
                · on demand
              </span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

const PRELOAD_TITLE: Record<string, string> = {
  idle: 'Interview mode is on. Nothing has been preloaded yet.',
  loading: 'Computing every curated step so none of them waits during the demo.',
  ready: 'Every curated step is served from a warm cache.',
  failed:
    'Preload did not complete, so curated steps compute on demand. Nothing is wrong with the ' +
    'results; they just arrive slower.',
};

function Segment({
  label,
  value,
  tone,
  title,
  mono,
}: {
  label: string;
  value: string;
  tone: 'normal' | 'warning' | 'critical' | 'info' | 'idle';
  title?: string;
  mono?: boolean;
}) {
  return (
    <span className="flex min-w-0 items-center gap-1.5" title={title}>
      <span className="label shrink-0">{label}</span>
      <StatusDot tone={tone} pulse={tone === 'normal'} />
      <span className={cn('truncate text-ink-200', mono && 'tabular font-mono')}>{value}</span>
    </span>
  );
}

function Rule() {
  return <span className="h-3 w-px shrink-0 bg-base-600" />;
}
