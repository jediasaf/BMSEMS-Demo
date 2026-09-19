import { cn } from '@/lib/format';
import type { AcceptanceVerdict } from '@/lib/types';

/**
 * A gate's criteria, rendered the same way wherever a gate appears.
 *
 * Both modules end in something that is allowed to say no -- the zone
 * simulator's verdict on a setpoint proposal, and the post-action load flow's
 * verdict on a dispatch. They are the same idea, so they read the same: the
 * criterion, whether it passed, and the measured margin that decided it.
 */
export function AcceptanceCriteria({ verdict }: { verdict: AcceptanceVerdict }) {
  return (
    <>
      <p
        className={cn(
          'text-2xs leading-relaxed',
          verdict.accepted ? 'text-ink-300' : 'text-status-critical',
        )}
      >
        {verdict.reason}
      </p>
      <ul className="mt-2 space-y-1 border-t border-base-700 pt-2">
        {verdict.criteria.map((criterion) => (
          <li
            key={criterion.criterion}
            className="flex items-baseline justify-between gap-2 text-3xs"
          >
            <span className="flex min-w-0 items-baseline gap-1.5">
              <span
                aria-hidden
                className={cn(
                  'shrink-0 font-mono',
                  criterion.passed ? 'text-accent' : 'text-status-critical',
                )}
              >
                {criterion.passed ? '✓' : '✗'}
              </span>
              {/* Not colour alone: the state is in the text for anyone who
                  cannot distinguish the tick from the cross. */}
              <span className="sr-only">{criterion.passed ? 'passed:' : 'failed:'}</span>
              <span className="text-ink-400">{criterion.criterion}</span>
            </span>
            <span className="tabular shrink-0 font-mono text-ink-200">{criterion.detail}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 border-t border-base-700 pt-2 text-3xs leading-relaxed text-ink-600">
        {verdict.note}
      </p>
    </>
  );
}
