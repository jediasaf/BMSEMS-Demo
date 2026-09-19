'use client';

import { History } from 'lucide-react';
import { shortDate } from '@/lib/format';

/**
 * Shown when a panel is displaying a recorded result rather than this
 * request's own computation.
 *
 * The values are real -- they were produced by the same code path, earlier --
 * so the panel is not wrong. It is stale, and a demo that quietly serves a
 * recording as fresh is the kind of thing this project exists not to do.
 */
export function ReplayNotice({ note, recordedAt }: { note?: string; recordedAt?: string | null }) {
  if (!note) return null;
  return (
    <div className="flex items-start gap-2 rounded-panel border border-prov-simulated/45 bg-prov-simulated/[0.07] px-2.5 py-1.5">
      <History className="mt-[1px] h-3 w-3 shrink-0 text-prov-simulated" />
      <div className="min-w-0">
        <div className="text-3xs font-semibold uppercase tracking-[0.1em] text-prov-simulated">
          Simulation replay
        </div>
        <p className="mt-0.5 text-3xs leading-relaxed text-ink-400">{note}</p>
        {recordedAt && (
          <p className="tabular mt-0.5 font-mono text-3xs text-ink-600">
            recorded {shortDate(recordedAt)}
          </p>
        )}
      </div>
    </div>
  );
}
