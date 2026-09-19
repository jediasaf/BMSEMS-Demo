'use client';

import { useEffect } from 'react';
import { api } from '@/lib/api';
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
  const { status, setStatus, window: replayWindow, cursor, interviewMode } = useDemo();

  useEffect(() => {
    let cancelled = false;
    api
      .status()
      .then((s) => !cancelled && setStatus(s))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [setStatus]);

  const stamp = cursorTimestamp(replayWindow, cursor);

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
          <Segment label="Replay" value={fullTimestamp(stamp)} tone="info" mono />
        </>
      )}

      <div className="ml-auto flex items-center gap-2.5">
        {status?.notes.length ? (
          <span
            className="hidden max-w-[40rem] truncate text-ink-600 xl:inline"
            title={status.notes.join('\n')}
          >
            {status.notes[0]}
          </span>
        ) : null}
        {interviewMode && (
          <span className="inline-flex items-center gap-1 rounded-pill border border-accent/40 bg-accent/10 px-1.5 py-[1px] text-3xs font-semibold uppercase tracking-[0.1em] text-accent">
            <StatusDot tone="normal" pulse />
            Interview mode
          </span>
        )}
      </div>
    </div>
  );
}

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
