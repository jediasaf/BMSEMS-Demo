'use client';

import { useState } from 'react';
import { PROVENANCE_STYLE, cn, fullTimestamp } from '@/lib/format';
import type { Provenance } from '@/lib/types';

/**
 * The badge that makes the whole platform auditable.
 *
 * Click it and you get the full chain: which source, which field, what was done
 * to it, and which assumptions were made. If a number cannot answer those
 * questions it should not be on screen.
 */
/** Three-letter codes keep the badge legible where a full word will not fit. */
const SHORT: Record<string, string> = {
  MEASURED: 'MEA',
  PREDICTED: 'PRE',
  SIMULATED: 'SIM',
  OPTIMISED: 'OPT',
  DERIVED: 'DER',
  INJECTED: 'INJ',
};

export function ProvenanceBadge({
  provenance,
  size = 'sm',
  showLabel = true,
  className,
}: {
  provenance: Provenance;
  size?: 'xs' | 'sm';
  showLabel?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const style = PROVENANCE_STYLE[provenance.source_type];

  return (
    <span className={cn('relative inline-flex', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        aria-expanded={open}
        aria-label={`Provenance: ${provenance.source_type}. ${style.blurb}`}
        className={cn(
          'focus-ring inline-flex items-center gap-1 rounded-pill border px-1.5 font-mono font-medium uppercase tracking-wider transition-colors hover:brightness-125',
          style.border,
          style.bg,
          style.text,
          size === 'xs' ? 'py-[1px] text-[10px]' : 'py-0.5 text-2xs',
        )}
      >
        <span className={cn('h-1 w-1 rounded-full', style.text.replace('text-', 'bg-'))} />
        {showLabel ? provenance.source_type : SHORT[provenance.source_type]}
        {provenance.is_fixture && <span className="text-status-warning">·FIXTURE</span>}
      </button>

      {open && (
        <div
          role="dialog"
          className="absolute left-0 top-[calc(100%+6px)] z-50 w-[22rem] max-w-[calc(100vw-2rem)] rounded-panel border border-base-500 bg-base-850 p-3 text-left shadow-2xl"
        >
          <div className="flex items-center justify-between gap-2 border-b border-base-600 pb-2">
            <span className={cn('font-mono text-2xs font-semibold uppercase', style.text)}>
              {provenance.source_type}
            </span>
            <span className="text-[10px] text-ink-500">{provenance.quality}</span>
          </div>
          <p className="mt-2 text-2xs leading-relaxed text-ink-300">{style.blurb}</p>

          <dl className="mt-2 space-y-1.5 border-t border-base-700 pt-2 text-2xs">
            <Row label="Source" value={provenance.source_name} />
            <Row label="Publisher" value={provenance.publisher} />
            {provenance.field && <Row label="Field" value={provenance.field} mono />}
            {provenance.engine_label && <Row label="Engine" value={provenance.engine_label} />}
            {provenance.model_id && <Row label="Model" value={provenance.model_id} mono />}
            {provenance.units && <Row label="Units" value={provenance.units} />}
            {provenance.timestamp && (
              <Row label="Timestamp" value={fullTimestamp(provenance.timestamp)} mono />
            )}
            {provenance.processing && <Row label="Processing" value={provenance.processing} />}
          </dl>

          {provenance.assumptions.length > 0 && (
            <div className="mt-2 border-t border-base-700 pt-2">
              <div className="text-[10px] uppercase tracking-wider text-ink-500">Assumptions</div>
              <ul className="mt-1 space-y-1">
                {provenance.assumptions.map((assumption) => (
                  <li key={assumption} className="flex gap-1.5 text-2xs leading-relaxed text-ink-300">
                    <span className="text-status-warning">·</span>
                    <span>{assumption}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {provenance.notes && (
            <p className="mt-2 border-t border-base-700 pt-2 text-2xs leading-relaxed text-ink-400">
              {provenance.notes}
            </p>
          )}

          {provenance.url && (
            <a
              href={provenance.url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 block truncate text-2xs text-accent hover:underline"
            >
              {provenance.url}
            </a>
          )}
        </div>
      )}
    </span>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[5.5rem_1fr] gap-2">
      <dt className="text-ink-500">{label}</dt>
      <dd className={cn('break-words text-ink-200', mono && 'font-mono text-[10px]')}>{value}</dd>
    </div>
  );
}
