'use client';

import { useState } from 'react';
import { ArrowRight, Check, Info, ShieldCheck, X } from 'lucide-react';
import { ProvenanceBadge } from './ProvenanceBadge';
import { Button, Meter, Pill } from './Primitives';
import { api } from '@/lib/api';
import { cn, num, signed } from '@/lib/format';
import type { Recommendation } from '@/lib/types';

/**
 * The most visually important card in the BMS.
 *
 * Note what it deliberately does *not* do: claim an energy saving. The impact
 * block stays empty until the Control Lab has run both cases through the
 * simulator, because a number invented here would be the easiest thing in the
 * whole platform to get wrong.
 */
export function RecommendationCard({
  recommendation,
  siteId,
  scenarioId,
  onSimulate,
  onDismiss,
  compact,
}: {
  recommendation: Recommendation;
  siteId: string;
  scenarioId: string;
  onSimulate?: () => void;
  onDismiss?: () => void;
  compact?: boolean;
}) {
  const [explaining, setExplaining] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<{
    valid: boolean;
    checks: { check: string; passed: boolean; detail: string }[];
    note: string;
  } | null>(null);

  const runValidation = async () => {
    setValidating(true);
    try {
      setValidation(await api.bms.validate(recommendation.recommendation_id, siteId, scenarioId));
    } catch {
      setValidation(null);
    } finally {
      setValidating(false);
    }
  };

  const delta = recommendation.proposed_value - recommendation.current_value;

  return (
    <div className="panel border-l-[2px] border-l-accent">
      <header className="panel-head">
        <div className="flex items-center gap-2">
          <span className="panel-title text-accent">AI recommendation</span>
          <Pill tone="accent">{recommendation.mode}</Pill>
        </div>
        <ProvenanceBadge provenance={recommendation.provenance} size="xs" />
      </header>

      <div className="space-y-2.5 p-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <h3 className="text-xs font-semibold text-ink-100">{recommendation.action}</h3>
          {recommendation.zone_id && <Pill tone="info">{recommendation.zone_id}</Pill>}
        </div>

        <div className="flex items-center gap-3 rounded-panel border border-base-600 bg-base-800/70 px-2.5 py-2">
          <div className="min-w-0">
            <div className="label">Current</div>
            <div className="tabular text-lg font-semibold leading-none text-ink-300">
              {num(recommendation.current_value)}
              <span className="ml-0.5 text-2xs font-normal text-ink-500">
                {recommendation.unit}
              </span>
            </div>
          </div>
          <ArrowRight className="h-3.5 w-3.5 shrink-0 text-accent" />
          <div className="min-w-0">
            <div className="label">Recommended</div>
            <div className="tabular text-lg font-semibold leading-none text-accent">
              {num(recommendation.proposed_value)}
              <span className="ml-0.5 text-2xs font-normal text-accent/70">
                {recommendation.unit}
              </span>
            </div>
          </div>
          <div className="ml-auto min-w-0 text-right">
            <div className="label">Change</div>
            <div className="tabular text-xs font-semibold text-ink-100">
              {signed(delta)} {recommendation.unit}
            </div>
          </div>
        </div>

        <div>
          <div className="label mb-1">Reason</div>
          <p className="text-2xs leading-relaxed text-ink-300">{recommendation.rationale}</p>
        </div>

        <div className="flex items-center gap-2 border-t border-base-700 pt-2">
          <span className="label shrink-0">Confidence</span>
          <Meter value={recommendation.confidence * 100} className="flex-1" />
          <span className="tabular shrink-0 text-2xs font-semibold text-accent">
            {num(recommendation.confidence * 100, 0)}%
          </span>
        </div>

        {recommendation.expected_impact && (
          <div className="rounded-panel border border-base-600 bg-base-800/50 px-2.5 py-2">
            <div className="label mb-1">Expected impact</div>
            <div className="flex items-start gap-1.5">
              <Info className="mt-[2px] h-3 w-3 shrink-0 text-status-info" />
              <div className="min-w-0">
                <p className="text-2xs leading-relaxed text-ink-300">
                  {recommendation.expected_impact.basis}
                </p>
                <div className="mt-1.5">
                  <ProvenanceBadge
                    provenance={recommendation.expected_impact.provenance}
                    size="xs"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {explaining && (
          <div className="space-y-2 rounded-panel border border-base-600 bg-base-800/60 p-2.5">
            <div className="label">Contributing factors</div>
            {recommendation.factors.map((factor) => (
              <div
                key={factor.feature}
                className="flex items-baseline justify-between gap-2 border-b border-base-700/50 py-1 last:border-b-0"
              >
                <span className="truncate text-2xs text-ink-400">{factor.label}</span>
                <span
                  className={cn(
                    'tabular shrink-0 font-mono text-2xs font-medium',
                    factor.direction === 'up'
                      ? 'text-status-warning'
                      : factor.direction === 'down'
                        ? 'text-status-info'
                        : 'text-ink-300',
                  )}
                >
                  {signed(factor.contribution)}
                  {factor.detail && (
                    <span className="ml-1.5 font-sans text-3xs text-ink-600">{factor.detail}</span>
                  )}
                </span>
              </div>
            ))}
            <p className="border-t border-base-700 pt-2 text-3xs leading-relaxed text-ink-600">
              Contributing factors describe what the model responded to. They are not evidence of
              cause.
            </p>
            <div className="border-t border-base-700 pt-2">
              <div className="label mb-1">Constraints checked</div>
              <ul className="space-y-0.5">
                {recommendation.constraints_checked.map((constraint) => (
                  <li key={constraint} className="flex items-center gap-1.5 text-2xs text-ink-300">
                    <Check className="h-2.5 w-2.5 shrink-0 text-status-normal" />
                    {constraint}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {validation && (
          <div
            className={cn(
              'rounded-panel border p-2.5',
              validation.valid
                ? 'border-status-normal/40 bg-status-normal/[0.06]'
                : 'border-status-critical/40 bg-status-critical/[0.06]',
            )}
          >
            <div className="flex items-center gap-1.5">
              <ShieldCheck
                className={cn(
                  'h-3.5 w-3.5',
                  validation.valid ? 'text-status-normal' : 'text-status-critical',
                )}
              />
              <span className="text-2xs font-semibold text-ink-100">
                Safety gate: {validation.valid ? 'passed' : 'blocked'}
              </span>
            </div>
            <ul className="mt-1.5 space-y-0.5">
              {validation.checks.map((check) => (
                <li key={check.check} className="flex items-start gap-1.5 text-3xs">
                  {check.passed ? (
                    <Check className="mt-[2px] h-2.5 w-2.5 shrink-0 text-status-normal" />
                  ) : (
                    <X className="mt-[2px] h-2.5 w-2.5 shrink-0 text-status-critical" />
                  )}
                  <span className="text-ink-400">
                    <span className="font-mono text-ink-200">{check.check}</span> — {check.detail}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 border-t border-base-700 pt-1.5 text-3xs text-ink-600">
              {validation.note}
            </p>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5 border-t border-base-700 pt-2">
          {onSimulate && (
            <Button variant="primary" size={compact ? 'sm' : 'md'} onClick={onSimulate}>
              Simulate action
            </Button>
          )}
          <Button size={compact ? 'sm' : 'md'} onClick={() => setExplaining((v) => !v)}>
            {explaining ? 'Hide explanation' : 'View explanation'}
          </Button>
          <Button size={compact ? 'sm' : 'md'} onClick={runValidation} disabled={validating}>
            {validating ? 'Checking…' : 'Run safety gate'}
          </Button>
          {onDismiss && (
            <Button variant="ghost" size={compact ? 'sm' : 'md'} onClick={onDismiss}>
              Dismiss
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
