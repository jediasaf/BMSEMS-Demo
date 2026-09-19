'use client';

import { useState } from 'react';
import { FlaskConical, Info } from 'lucide-react';
import { cn } from '@/lib/format';
import type { Scenario, ScenarioInjection } from '@/lib/types';
import { Pill } from './Primitives';

export function ScenarioSelector({
  scenarios,
  selected,
  onSelect,
  injection,
}: {
  scenarios: Scenario[];
  selected: string;
  onSelect: (id: string) => void;
  injection?: ScenarioInjection | null;
}) {
  const [detail, setDetail] = useState<string | null>(null);
  const active = scenarios.find((s) => s.scenario_id === selected);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        {scenarios.map((scenario) => (
          <button
            key={scenario.scenario_id}
            type="button"
            onClick={() => onSelect(scenario.scenario_id)}
            className={cn(
              'focus-ring inline-flex items-center gap-1.5 rounded-panel border px-2 py-[3px] text-2xs font-medium transition-colors',
              selected === scenario.scenario_id
                ? 'border-accent/50 bg-accent/12 text-accent'
                : 'border-base-600 bg-base-800/60 text-ink-300 hover:border-base-500 hover:text-ink-100',
            )}
          >
            {!scenario.is_baseline && <FlaskConical className="h-3 w-3" />}
            {scenario.name}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setDetail(detail ? null : selected)}
          aria-label="About this scenario"
          className="focus-ring ml-0.5 rounded-panel p-1 text-ink-400 hover:text-ink-100"
        >
          <Info className="h-3 w-3" />
        </button>
      </div>

      {injection && (
        <div className="flex flex-wrap items-center gap-2 rounded-panel border border-prov-injected/40 bg-prov-injected/[0.07] px-2 py-1">
          <Pill tone="neutral" className="border-prov-injected/50 text-prov-injected">
            Injected scenario
          </Pill>
          <span className="tabular text-3xs text-ink-200">
            peak <span className="font-semibold text-prov-injected">+{injection.peak_injection.toFixed(1)} {injection.unit}</span>
            {' · '}
            {injection.total_injection.toFixed(0)} kWh over {injection.affected_steps} intervals
          </span>
          <span className="ml-auto font-mono text-3xs text-ink-600">seed {injection.seed}</span>
        </div>
      )}

      {detail && active && (
        <div className="rounded-panel border border-base-600 bg-base-800/60 p-2.5">
          <div className="text-2xs font-semibold text-ink-100">{active.name}</div>
          <div className="label">{active.subtitle}</div>
          <p className="mt-1.5 text-2xs leading-relaxed text-ink-300">{active.description}</p>
          <p className="mt-1.5 border-t border-base-700 pt-1.5 text-2xs leading-relaxed text-ink-400">
            <span className="text-ink-500">What it demonstrates — </span>
            {active.teaches}
          </p>
          {Object.keys(active.parameters).length > 0 && (
            <dl className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 border-t border-base-700 pt-1.5">
              {Object.entries(active.parameters).map(([key, value]) => (
                <div key={key} className="flex gap-1.5 text-[10px]">
                  <dt className="text-ink-500">{key}</dt>
                  <dd className="tabular font-mono text-ink-200">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
