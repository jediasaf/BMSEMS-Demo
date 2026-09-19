'use client';

import { useEffect } from 'react';
import { Activity, Cpu, Database, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';
import { useDemo } from '@/lib/store';
import { cn } from '@/lib/format';
import { Pill, StatusDot } from './Primitives';

/**
 * The demo status bar. Always visible, always honest: it says where the data
 * came from, whether models are online, and which simulation engine is live.
 */
export function StatusBar() {
  const { status, setStatus, interviewMode, setInterviewMode, reset } = useDemo();

  useEffect(() => {
    let cancelled = false;
    api
      .status()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [setStatus]);

  const onReset = async () => {
    reset();
    try {
      await api.resetDemo();
    } catch {
      /* a failed cache reset is not worth breaking the demo over */
    }
    window.location.reload();
  };

  return (
    <div className="flex h-8 items-center gap-3 border-b border-base-600/70 bg-base-850/90 px-3 text-2xs backdrop-blur">
      <Item
        icon={<Database className="h-3 w-3" />}
        label="Data"
        value={status?.data_label ?? '…'}
        tone={status ? (status.data_ok ? 'normal' : 'warning') : 'idle'}
        title={status?.source_name}
      />
      <Divider />
      <Item
        icon={<Cpu className="h-3 w-3" />}
        label="AI"
        value={status?.ai_label ?? '…'}
        tone={status ? (status.ai_ok ? 'normal' : 'warning') : 'idle'}
      />
      <Divider />
      <Item
        icon={<Activity className="h-3 w-3" />}
        label="Simulation"
        value={status?.simulation_label ?? '…'}
        tone={
          status
            ? status.simulation_engine === 'BOPTEST'
              ? 'normal'
              : 'info'
            : 'idle'
        }
        title={status?.notes.join(' ')}
      />

      <div className="ml-auto flex items-center gap-2">
        {status?.notes.length ? (
          <span
            className="hidden max-w-[34rem] truncate text-ink-500 lg:inline"
            title={status.notes.join('\n')}
          >
            {status.notes[0]}
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => setInterviewMode(!interviewMode)}
          className="focus-ring"
          title="Interview mode preloads curated data, hides unfinished surface and keeps latency low."
        >
          <Pill tone={interviewMode ? 'accent' : 'neutral'}>
            <StatusDot tone={interviewMode ? 'normal' : 'idle'} />
            Interview mode
          </Pill>
        </button>
        <button
          type="button"
          onClick={onReset}
          className="focus-ring inline-flex items-center gap-1 rounded-pill border border-base-500 px-1.5 py-0.5 text-2xs text-ink-300 transition-colors hover:border-base-400 hover:text-ink-100"
          title="Clear every server-side cache and restore the default scenario"
        >
          <RotateCcw className="h-2.5 w-2.5" />
          Reset demo
        </button>
      </div>
    </div>
  );
}

function Item({
  icon,
  label,
  value,
  tone,
  title,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: 'normal' | 'warning' | 'critical' | 'info' | 'idle';
  title?: string;
}) {
  return (
    <span className="flex items-center gap-1.5" title={title}>
      <span className="text-ink-500">{icon}</span>
      <span className="uppercase tracking-wider text-ink-500">{label}</span>
      <StatusDot tone={tone} pulse={tone === 'normal'} />
      <span className={cn('font-medium text-ink-200')}>{value}</span>
    </span>
  );
}

function Divider() {
  return <span className="h-3 w-px bg-base-600" />;
}
