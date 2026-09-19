'use client';

import Link from 'next/link';
import { Building2, Zap } from 'lucide-react';
import { useDemo } from '@/lib/store';
import { Button, Panel, Pill } from '@/components/Primitives';
import { PROVENANCE_STYLE } from '@/lib/format';
import type { SourceType } from '@/lib/types';

const FLOWS = [
  {
    href: '/bms',
    icon: Building2,
    name: 'EcoTwin BMS',
    subtitle: 'AI Building Operator',
    accent: 'text-teal',
    steps: ['Measured', 'Detect', 'Predict', 'Recommend', 'Simulate', 'Compare'],
    detail:
      'Metered building demand and published weather, a day-ahead gradient-boosted forecast with a calibrated interval, residual anomaly detection against an hour-of-day baseline, a constrained setpoint proposal, and an HVAC control case scored by a building simulator.',
  },
  {
    href: '/ems',
    icon: Zap,
    name: 'EcoTwin EMS',
    subtitle: 'AI Power Operator',
    accent: 'text-accent',
    steps: ['Measured', 'Forecast', 'Detect risk', 'Optimise', 'Simulate', 'Resolve'],
    detail:
      'The same facilities as an electrical estate: demand forecast onto a pandapower LV model, transformer and voltage risk over a forward horizon, and a linear program that shifts EV charging and buys HVAC flexibility — verified by a second load flow.',
  },
];

const PROVENANCE_ORDER: SourceType[] = [
  'MEASURED',
  'PREDICTED',
  'SIMULATED',
  'OPTIMISED',
  'DERIVED',
  'INJECTED',
];

export default function Home() {
  const { startTour, status } = useDemo();

  return (
    <div className="mx-auto max-w-6xl space-y-3">
      <section className="panel grid-lines overflow-hidden">
        <div className="bg-gradient-to-br from-base-850/40 to-base-900/80 p-6">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="accent">EcoStruxure-ready architecture</Pill>
            <Pill tone="neutral">Portfolio prototype</Pill>
            {status && (
              <Pill tone={status.data_ok ? 'info' : 'warning'}>{status.data_label}</Pill>
            )}
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-ink-100">
            EcoTwin AI
          </h1>
          <p className="text-sm text-ink-300">AI Building &amp; Power Operations Platform</p>
          <p className="mt-3 max-w-3xl text-xs leading-relaxed text-ink-400">
            Two working end-to-end operational AI workflows over real public Schneider Electric
            data. Measured, predicted, simulated, optimised and injected values are separated
            everywhere and never blended: click any badge to see the source, the field, the
            processing chain and the assumptions behind a number.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="primary" onClick={startTour}>
              Start the guided demo
            </Button>
            <Link href="/bms">
              <Button>Open EcoTwin BMS</Button>
            </Link>
            <Link href="/ems">
              <Button>Open EcoTwin EMS</Button>
            </Link>
          </div>
        </div>
      </section>

      <div className="grid gap-3 lg:grid-cols-2">
        {FLOWS.map((flow) => {
          const Icon = flow.icon;
          return (
            <Link key={flow.href} href={flow.href} className="focus-ring group">
              <Panel className="h-full transition-colors group-hover:border-accent/40">
                <div className="flex items-start gap-3">
                  <span className="rounded-panel bg-base-700/70 p-2">
                    <Icon className={`h-5 w-5 ${flow.accent}`} />
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-ink-100">{flow.name}</h2>
                    <p className="text-2xs text-ink-400">{flow.subtitle}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1">
                  {flow.steps.map((step, index) => (
                    <span key={step} className="flex items-center gap-1">
                      <span className="rounded-pill border border-base-500 bg-base-700/60 px-1.5 py-0.5 text-[10px] text-ink-300">
                        {step}
                      </span>
                      {index < flow.steps.length - 1 && (
                        <span className="text-ink-600">→</span>
                      )}
                    </span>
                  ))}
                </div>
                <p className="mt-3 text-2xs leading-relaxed text-ink-400">{flow.detail}</p>
              </Panel>
            </Link>
          );
        })}
      </div>

      <Panel title="Provenance vocabulary" subtitle="enforced in the backend, not by convention">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {PROVENANCE_ORDER.map((type) => {
            const style = PROVENANCE_STYLE[type];
            return (
              <div
                key={type}
                className={`rounded-panel border ${style.border} ${style.bg} p-2.5`}
              >
                <div className={`font-mono text-2xs font-semibold uppercase ${style.text}`}>
                  {type}
                </div>
                <p className="mt-1 text-[10px] leading-relaxed text-ink-400">{style.blurb}</p>
              </div>
            );
          })}
        </div>
        <p className="mt-2.5 border-t border-base-700 pt-2.5 text-[10px] leading-relaxed text-ink-500">
          A value cannot be tagged MEASURED unless its registered source is a real measurement, and
          cannot be tagged SIMULATED without naming the engine that produced it. Both rules are
          validators on the provenance model, so a mislabelled number fails at construction rather
          than reaching a chart.
        </p>
      </Panel>
    </div>
  );
}
