'use client';

import { useState } from 'react';
import { ArrowRight, Check, Info, ShieldCheck, X } from 'lucide-react';
import { ProvenanceBadge } from './ProvenanceBadge';
import { Button, Pill } from './Primitives';
import { api } from '@/lib/api';
import { cn, num, signed } from '@/lib/format';
import type { Recommendation } from '@/lib/types';

export function RecommendationCard({
  recommendation,
  siteId,
  scenarioId,
  onSimulate,
  onDismiss,
}: {
  recommendation: Recommendation;
  siteId: string;
  scenarioId: string;
  onSimulate?: () => void;
  onDismiss?: () => void;
}) {
  const [explaining, setExplaining] = useState(false);
  const [validation, setValidation] = useState<
    { valid: boolean; checks: { check: string; passed: boolean; detail: string }[]; note: string } | null
  >(null);
  const [validating, setValidating] = useState(false);

  const runValidation = async () => {
    setValidating(true);
    try {
      const result = await api.bms.validate(recommendation.recommendation_id, siteId, scenarioId);
      setValidation(result);
    } catch {
      setValidation(null);
    } finally {
      setValidating(false);
    }
  };

  const delta = recommendation.proposed_value - recommendation.current_value;

  return (
    <div className="panel border-l-2 border-l-accent/70">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <span className="panel-title text-accent">AI recommendation</span>
          <Pill tone="accent">{recommendation.mode}</Pill>
        </div>
        <ProvenanceBadge provenance={recommendation.provenance} size="xs" />
      </div>

      <div className="space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-ink-100">{recommendation.action}</h3>
          {recommendation.zone_id && <Pill tone="info">{recommendation.zone_id}</Pill>}
        </div>

        <div className="flex items-center gap-3 rounded-panel bg-base-850/70 p-2.5">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-ink-500">Current</div>
            <div className="tabular text-xl font-semibold text-ink-200">
              {num(recommendation.current_value)}
              <span className="ml-0.5 text-xs text-ink-400">{recommendation.unit}</span>
            </div>
          </div>
          <ArrowRight className="h-4 w-4 shrink-0 text-accent" />
          <div>
            <div className="text-[10px] uppercase tracking-wider text-ink-500">Recommended</div>
            <div className="tabular text-xl font-semibold text-accent">
              {num(recommendation.proposed_value)}
              <span className="ml-0.5 text-xs text-accent/70">{recommendation.unit}</span>
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-[10px] uppercase tracking-wider text-ink-500">Change</div>
            <div className="tabular text-sm font-semibold text-ink-100">
              {signed(delta)} {recommendation.unit}
            </div>
          </div>
        </div>

        <p className="text-2xs leading-relaxed text-ink-300">{recommendation.rationale}</p>

        <div className="flex items-center justify-between gap-3 border-t border-base-700 pt-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-ink-500">Confidence</span>
            <div className="h-1 w-20 overflow-hidden rounded-full bg-base-600">
              <div
                className="h-full bg-accent"
                style={{ width: `${recommendation.confidence * 100}%` }}
              />
            </div>
            <span className="tabular text-2xs font-semibold text-accent">
              {num(recommendation.confidence * 100, 0)}%
            </span>
          </div>
        </div>

        {recommendation.expected_impact && (
          <div className="rounded-panel border border-base-600 bg-base-850/50 p-2">
            <div className="flex items-start gap-1.5">
              <Info className="mt-0.5 h-3 w-3 shrink-0 text-status-info" />
              <div className="min-w-0">
                <div className="text-2xs text-ink-200">{recommendation.expected_impact.basis}</div>
                <div className="mt-1">
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
          <div className="space-y-2 rounded-panel border border-base-600 bg-base-850/60 p-2.5">
            <h4 className="text-[10px] uppercase tracking-wider text-ink-500">
              Contributing factors
            </h4>
            <ul className="space-y-1.5">
              {recommendation.factors.map((factor) => (
                <li key={factor.feature} className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-2xs text-ink-300">{factor.label}</span>
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
                      <span className="ml-1 font-sans text-ink-500">{factor.detail}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            <p className="border-t border-base-700 pt-2 text-[10px] leading-relaxed text-ink-500">
              Contributing factors describe what the model responded to. They are not evidence of
              cause.
            </p>

            <div className="border-t border-base-700 pt-2">
              <h4 className="text-[10px] uppercase tracking-wider text-ink-500">
                Constraints checked
              </h4>
              <ul className="mt-1 space-y-0.5">
                {recommendation.constraints_checked.map((constraint) => (
                  <li key={constraint} className="flex items-center gap-1.5 text-2xs text-ink-300">
                    <Check className="h-3 w-3 shrink-0 text-status-normal" />
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
                ? 'border-status-normal/40 bg-status-normal/5'
                : 'border-status-critical/40 bg-status-critical/5',
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
                <li key={check.check} className="flex items-start gap-1.5 text-[10px]">
                  {check.passed ? (
                    <Check className="mt-0.5 h-2.5 w-2.5 shrink-0 text-status-normal" />
                  ) : (
                    <X className="mt-0.5 h-2.5 w-2.5 shrink-0 text-status-critical" />
                  )}
                  <span className="text-ink-300">
                    <span className="font-mono text-ink-200">{check.check}</span> — {check.detail}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 border-t border-base-700 pt-1.5 text-[10px] text-ink-500">
              {validation.note}
            </p>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5 border-t border-base-700 pt-2.5">
          {onSimulate && (
            <Button variant="primary" size="sm" onClick={onSimulate}>
              Simulate in Control Lab
            </Button>
          )}
          <Button size="sm" onClick={() => setExplaining((v) => !v)}>
            {explaining ? 'Hide explanation' : 'View explanation'}
          </Button>
          <Button size="sm" onClick={runValidation} disabled={validating}>
            {validating ? 'Checking…' : 'Run safety gate'}
          </Button>
          {onDismiss && (
            <Button variant="ghost" size="sm" onClick={onDismiss}>
              Dismiss
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
