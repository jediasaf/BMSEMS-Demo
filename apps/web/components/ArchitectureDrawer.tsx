'use client';

import { useEffect, useState } from 'react';
import { Network, X } from 'lucide-react';
import { useDemo } from '@/lib/store';
import { PROVENANCE_STYLE, cn } from '@/lib/format';
import type { SourceType } from '@/lib/types';

/**
 * The closing slide, as a drawer rather than a page.
 *
 * Both pipelines as they actually run, with the component that does each step
 * named. Everything here is a claim the rest of the product backs up: the
 * engine label comes from the running simulation engine, not from a wish.
 */

const BMS_CHAIN = [
  { stage: 'Schneider public dataset', detail: '15-min metered demand + weather' },
  { stage: 'Adapter', detail: 'the only layer that knows field names' },
  { stage: 'LightGBM forecast', detail: 'conformalised 80% interval' },
  { stage: 'Residual anomaly', detail: 'robust z vs an hour-of-day baseline' },
  { stage: 'Recommendation', detail: 'constrained setpoint proposal' },
  { stage: 'Zone simulator', detail: 'baseline and proposal, same engine' },
  { stage: 'Acceptance gate', detail: 'the simulator may reject the proposal' },
];

const EMS_CHAIN = [
  { stage: 'Schneider public dataset', detail: 'per-facility demand' },
  { stage: 'LightGBM forecast', detail: '12 h forward horizon' },
  { stage: 'pandapower', detail: 'balanced AC load flow, six-bus LV model' },
  { stage: 'Risk assessment', detail: 'peak against a calibrated capacity' },
  { stage: 'CVXPY optimiser', detail: 'linear program over flexible load' },
  { stage: 'pandapower again', detail: 'the result, solved independently' },
];

const LEGEND: SourceType[] = [
  'MEASURED',
  'DERIVED',
  'PREDICTED',
  'SIMULATED',
  'OPTIMISED',
  'INJECTED',
];

export function ArchitectureDrawer({ onClose }: { onClose: () => void }) {
  const { status } = useDemo();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-base-950/70" onClick={onClose}>
      <aside
        role="dialog"
        aria-label="Architecture"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-[34rem] animate-fade-up flex-col border-l border-base-600 bg-base-900 shadow-raised"
      >
        <header className="flex h-topbar shrink-0 items-center justify-between gap-3 border-b border-base-600/70 px-3">
          <div className="flex items-center gap-2">
            <Network className="h-3.5 w-3.5 text-accent" />
            <h2 className="panel-title">Architecture</h2>
            <span className="panel-sub">what runs, in order</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close architecture"
            className="focus-ring rounded-panel p-1 text-ink-500 hover:text-ink-100"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          <Chain
            title="EcoTwin BMS"
            subtitle="measured → detect → predict → recommend → simulate → compare"
            tone="text-accent"
            steps={BMS_CHAIN}
          />
          <Chain
            title="EcoTwin EMS"
            subtitle="measured → forecast → detect risk → optimise → simulate → resolve"
            tone="text-info"
            steps={EMS_CHAIN}
          />

          <section className="rounded-panel border border-base-600 bg-base-850/70 p-2.5">
            <div className="label mb-1.5">Cross-module link</div>
            <p className="text-2xs leading-relaxed text-ink-400">
              EMS names the flexible contributors at the forecast peak, BMS answers by running its
              zone simulator on an HVAC reduction, and EMS re-solves the network with that reduction
              applied. A thermal simulation feeding an electrical one.
            </p>
          </section>

          <section className="rounded-panel border border-base-600 bg-base-850/70 p-2.5">
            <div className="label mb-1.5">Provenance vocabulary</div>
            <div className="grid grid-cols-2 gap-1.5">
              {LEGEND.map((type) => {
                const style = PROVENANCE_STYLE[type];
                return (
                  <div key={type} className="flex items-start gap-1.5">
                    <span
                      className={cn(
                        'mt-[1px] shrink-0 rounded-pill border px-1 py-[1px] font-mono text-3xs font-semibold',
                        style.border,
                        style.bg,
                        style.text,
                      )}
                    >
                      {type}
                    </span>
                    <span className="text-3xs leading-relaxed text-ink-500">{style.blurb}</span>
                  </div>
                );
              })}
            </div>
            <p className="mt-2 border-t border-base-700 pt-2 text-3xs leading-relaxed text-ink-600">
              Two of these are validators, not conventions: a value cannot be tagged MEASURED unless
              its registered source is a real measurement, and cannot be tagged SIMULATED without
              naming the engine that produced it.
            </p>
          </section>

          <section className="rounded-panel border border-base-600 bg-base-850/70 p-2.5">
            <div className="label mb-1.5">Running now</div>
            <dl className="space-y-1">
              <Row label="Data" value={status?.data_label ?? '…'} />
              <Row label="Models" value={status?.ai_label ?? '…'} />
              <Row label="Zone simulation" value={status?.simulation_label ?? '…'} />
              <Row label="Network" value="pandapower, balanced AC load flow" />
              <Row label="Actuation" value="none — advisory only, no controller path" />
            </dl>
          </section>
        </div>
      </aside>
    </div>
  );
}

function Chain({
  title,
  subtitle,
  tone,
  steps,
}: {
  title: string;
  subtitle: string;
  tone: string;
  steps: { stage: string; detail: string }[];
}) {
  return (
    <section className="rounded-panel border border-base-600 bg-base-850/70 p-2.5">
      <div className="flex items-baseline gap-2">
        <h3 className={cn('text-2xs font-semibold uppercase tracking-[0.13em]', tone)}>{title}</h3>
        <span className="panel-sub truncate">{subtitle}</span>
      </div>
      <ol className="mt-2 space-y-1">
        {steps.map((step, index) => (
          <li key={step.stage} className="flex items-start gap-2">
            <span className="mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-panel border border-base-500 font-mono text-[9px] text-ink-500">
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <span className="text-2xs text-ink-100">{step.stage}</span>
              <span className="ml-1.5 text-3xs text-ink-600">{step.detail}</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-2xs">
      <dt className="shrink-0 text-ink-500">{label}</dt>
      <dd className="truncate text-right text-ink-200">{value}</dd>
    </div>
  );
}

/** Small hook so both the system bar and the guided demo can open the drawer. */
export function useArchitectureDrawer() {
  const [open, setOpen] = useState(false);
  return { open, show: () => setOpen(true), hide: () => setOpen(false) };
}
