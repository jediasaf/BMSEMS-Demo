'use client';

import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { PROVENANCE_STYLE, cn, fullTimestamp } from '@/lib/format';
import type { Provenance } from '@/lib/types';

/** Three-letter codes keep the badge legible where a full word will not fit. */
/** Keep in step with the w-[23rem] on the panel below. */
const PANEL_WIDTH_PX = 368;

const SHORT: Record<string, string> = {
  MEASURED: 'MEA',
  PREDICTED: 'PRE',
  SIMULATED: 'SIM',
  OPTIMISED: 'OPT',
  DERIVED: 'DER',
  INJECTED: 'INJ',
};

/**
 * The badge that makes the platform auditable.
 *
 * Click it and you get the whole chain: type, source, field, processing and
 * assumptions. A number that cannot answer those questions has no business
 * being on screen, so every value-bearing element carries one of these.
 */
export function ProvenanceBadge({
  provenance,
  size = 'sm',
  showLabel = true,
  align = 'left',
  className,
}: {
  provenance: Provenance;
  size?: 'xs' | 'sm';
  showLabel?: boolean;
  /** Which edge the popover hangs from — 'right' for a badge near the right
   *  edge of a narrow tile, where a left-anchored panel would run off it. */
  align?: 'left' | 'right';
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<'left' | 'right'>(align);
  const ref = useRef<HTMLSpanElement>(null);
  const style = PROVENANCE_STYLE[provenance.source_type];

  // Flip the panel to whichever side keeps it inside the workspace. A badge in
  // the first KPI tile and one in the last need opposite anchors, and neither
  // knows where it sits until it is on screen.
  useEffect(() => {
    if (!open || !ref.current) return;
    const badge = ref.current.getBoundingClientRect();
    const bounds = ref.current.closest('main')?.getBoundingClientRect();
    const min = (bounds?.left ?? 0) + 8;
    const max = (bounds?.right ?? window.innerWidth) - 8;
    const fitsLeftAnchored = badge.left + PANEL_WIDTH_PX <= max;
    const fitsRightAnchored = badge.right - PANEL_WIDTH_PX >= min;
    if (align === 'right') setPlacement(fitsRightAnchored || !fitsLeftAnchored ? 'right' : 'left');
    else setPlacement(fitsLeftAnchored || !fitsRightAnchored ? 'left' : 'right');
  }, [open, align]);

  // Close on outside click / Escape rather than on blur: blur fires when the
  // pointer enters the popover itself, which made the content unselectable.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <span ref={ref} className={cn('relative inline-flex', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`Data provenance: ${provenance.source_type}. ${style.blurb}`}
        className={cn(
          'focus-ring inline-flex items-center gap-1 rounded-pill border font-mono font-semibold uppercase tracking-[0.08em] transition-colors hover:brightness-125',
          style.border,
          style.bg,
          style.text,
          size === 'xs' ? 'px-1 py-0 text-3xs' : 'px-1.5 py-[1px] text-3xs',
        )}
      >
        {showLabel ? provenance.source_type : SHORT[provenance.source_type]}
        {provenance.is_fixture && <span className="text-status-warning">·FIX</span>}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Data provenance"
          className={cn(
            'absolute top-[calc(100%+5px)] z-50 w-[23rem] max-w-[calc(100vw-2rem)] animate-fade-up rounded-panel border border-base-500 bg-base-850 text-left shadow-raised',
            placement === 'right' ? 'right-0' : 'left-0',
          )}
        >
          <div className="flex items-center justify-between gap-2 border-b border-base-600 px-2.5 py-1.5">
            <span className="label">Data provenance</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="focus-ring text-ink-500 hover:text-ink-200"
            >
              <X className="h-3 w-3" />
            </button>
          </div>

          <div className="px-2.5 py-2">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'rounded-pill border px-1.5 py-[1px] font-mono text-3xs font-semibold uppercase tracking-[0.08em]',
                  style.border,
                  style.bg,
                  style.text,
                )}
              >
                {provenance.source_type}
              </span>
              <span className="text-3xs uppercase tracking-[0.08em] text-ink-600">
                quality {provenance.quality}
              </span>
            </div>
            <p className="mt-1.5 text-2xs leading-relaxed text-ink-400">{style.blurb}</p>

            <dl className="mt-2 border-t border-base-700 pt-2">
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
                <div className="label">Assumptions</div>
                <ul className="mt-1 space-y-1">
                  {provenance.assumptions.map((assumption) => (
                    <li
                      key={assumption}
                      className="flex gap-1.5 text-2xs leading-relaxed text-ink-400"
                    >
                      <span className="shrink-0 text-status-warning">·</span>
                      <span>{assumption}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {provenance.notes && (
              <p className="mt-2 border-t border-base-700 pt-2 text-2xs leading-relaxed text-ink-500">
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
        </div>
      )}
    </span>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[5rem_1fr] gap-2 py-[2px]">
      <dt className="text-2xs text-ink-600">{label}</dt>
      <dd className={cn('break-words text-2xs text-ink-200', mono && 'font-mono text-3xs')}>
        {value}
      </dd>
    </div>
  );
}
