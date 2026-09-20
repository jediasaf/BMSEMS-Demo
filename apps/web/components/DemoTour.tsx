'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ChevronLeft, RotateCcw, X } from 'lucide-react';
import { useDemo } from '@/lib/store';
import { cn } from '@/lib/format';
import { Button } from './Primitives';
import { ArchitectureDrawer } from './ArchitectureDrawer';

/**
 * The four-to-six minute walkthrough.
 *
 * Each step owns its route and its scenario, so a stray click cannot knock the
 * demo off course: stepping forward or back re-applies both. The step list
 * mirrors `/interview/plan` on the backend, which is what the smoke test
 * drives and what `/interview/verify` checks the claims of.
 */

interface TourStep {
  title: string;
  body: string;
  href: string;
  /** Applied on entry, every time, so back and forward are symmetric. */
  bmsScenario?: string;
  emsScenario?: string;
  /** Opens the architecture drawer instead of navigating away. */
  architecture?: boolean;
}

const STEPS: TourStep[] = [
  {
    title: 'The building as recorded',
    body: 'Real 15-minute metered demand from the Schneider / DrivenData public competition dataset, replayed against its own clock, with the nearest published weather station. Every value carries a provenance badge: the load reads DERIVED because the publisher never states a unit for its energy counter, outdoor air reads MEASURED.',
    href: '/bms',
    bmsScenario: 'bms_normal_day',
  },
  {
    title: 'Inject the hot day',
    body: 'A seeded disturbance, added on top of the measurement and never replacing it — both series stay charted and the banner says INJECTED SCENARIO. Outdoor air is raised 7 K with a mid-afternoon emphasis, and the load follows through this building’s own fitted cooling sensitivity.',
    href: '/bms',
    bmsScenario: 'bms_hot_day',
  },
  {
    title: 'Detection, and why it is believable',
    body: 'The detector scores the forecast residual against an hour-of-day baseline calibrated on history that ends where this window begins — so a fault lasting the whole window cannot quietly become the new normal. Observed against expected, the robust z-score, the sustain requirement and the possible causes are all on screen.',
    href: '/bms/ai-operations',
    bmsScenario: 'bms_hot_day',
  },
  {
    title: 'The recommendation',
    body: 'A constrained setpoint proposal with its contributing factors, the constraints it was checked against, and a safety gate you can run. It claims no saving at this point — nothing is asserted before the simulator has run.',
    href: '/bms/ai-operations',
    bmsScenario: 'bms_hot_day',
  },
  {
    title: 'Simulate it, then let the simulator judge',
    body: 'The optimiser solves a linear program over the same two-node zone model the simulator integrates, with installed plant capacity as a constraint. The proposal then goes back through the full nonlinear simulator, and is rejected if it does not beat doing nothing. Energy, peak and comfort are the simulator’s answer, not the optimiser’s.',
    href: '/bms/control-lab',
    bmsScenario: 'bms_hot_day',
  },
  {
    title: 'EcoTwin EMS — the portfolio',
    body: 'The same metered facilities seen as an electrical estate. Transformer ratings are DERIVED from observed peaks by standard sizing practice, because the dataset publishes no nameplate data — and the badge says so. Capacity is calibrated by bisection on the load flow, not by kVA × power factor.',
    href: '/ems',
    emsScenario: 'ems_normal_day',
  },
  {
    title: 'Start the EV charging surge',
    body: 'A seeded 120 kW charging session lands on the flexible feeder each afternoon, additive to the measured demand. This is load the transformer was never sized for — unlike a peak day, which a correctly sized transformer survives.',
    href: '/ems/scenario-lab',
    emsScenario: 'ems_ev_surge',
  },
  {
    title: 'What it does to the network',
    body: 'pandapower solves a balanced AC load flow over a six-bus LV model with catalogue cable impedances. The transformer goes past nameplate and the LV bus sags. Nothing here is hard-coded — every number is a solve, and all of it is labelled SIMULATED.',
    href: '/ems/network',
    emsScenario: 'ems_ev_surge',
  },
  {
    title: 'Optimise: shift the energy, do not shed it',
    body: 'Click Run optimisation — this is the one step that computes on demand, and watching it solve is the point. A linear program defers EV charging and buys HVAC flexibility within a comfort budget. EV energy is conserved as a hard equality and recovery can never precede curtailment, or the optimiser would charge vehicles that have not arrived.',
    href: '/ems/scenario-lab',
    emsScenario: 'ems_ev_surge',
  },
  {
    title: 'Verify with a second load flow',
    body: 'The before and after transformer figures are two independent pandapower solves at the worst instant — not the optimiser marking its own homework. Below them is the network verdict: seven criteria read off the post-action load flow, including that the EV energy was deferred rather than shed. It is allowed to reject the dispatch, and a rejection claims nothing.',
    href: '/ems/scenario-lab',
    emsScenario: 'ems_ev_surge',
  },
  {
    title: 'Provenance: click any badge',
    body: 'Six categories, one closed vocabulary, enforced in the backend: a value cannot be tagged MEASURED unless its registered source is a real measurement, and cannot be tagged SIMULATED without naming the engine that produced it. A mislabelled number fails at construction rather than reaching a chart.',
    href: '/bms',
    bmsScenario: 'bms_hot_day',
  },
  {
    title: 'Both pipelines, end to end',
    body: 'Two workflows over one provenance model, one replay clock and one adapter layer — which is what makes the source swappable for EcoStruxure Building Operation or Power Monitoring Expert without touching the analytics. This is a portfolio prototype, not a Schneider Electric product.',
    href: '/bms',
    architecture: true,
  },
];

export function DemoTour() {
  const router = useRouter();
  const {
    tourStep,
    nextTourStep,
    prevTourStep,
    endTour,
    resetDemo,
    setBmsScenario,
    setEmsScenario,
  } = useDemo();
  const [architecture, setArchitecture] = useState(false);

  const step = tourStep !== null ? STEPS[tourStep] : undefined;

  useEffect(() => {
    if (!step) {
      setArchitecture(false);
      return;
    }
    if (step.bmsScenario) setBmsScenario(step.bmsScenario);
    if (step.emsScenario) setEmsScenario(step.emsScenario);
    setArchitecture(Boolean(step.architecture));
    router.push(step.href);
  }, [tourStep]); // eslint-disable-line react-hooks/exhaustive-deps

  if (tourStep === null || !step) return null;
  const isLast = tourStep === STEPS.length - 1;

  return (
    <>
      {architecture && <ArchitectureDrawer onClose={() => setArchitecture(false)} />}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center p-3">
        <div className="pointer-events-auto w-full max-w-3xl animate-fade-up rounded-panel border border-accent/40 bg-base-850/[0.97] shadow-raised backdrop-blur">
          <div className="flex items-center justify-between gap-2 border-b border-base-700 px-2.5 py-1.5">
            <span className="label text-accent">Guided demo</span>
            <div className="flex items-center gap-2">
              <span className="tabular font-mono text-3xs text-ink-500">
                step {tourStep + 1} of {STEPS.length}
              </span>
              <button
                type="button"
                onClick={() => {
                  resetDemo();
                  router.push('/bms');
                }}
                title="Reset the demo to its opening position"
                className="focus-ring flex items-center gap-1 rounded-panel p-0.5 text-3xs uppercase tracking-[0.08em] text-ink-500 hover:text-ink-100"
              >
                <RotateCcw className="h-3 w-3" />
                Reset
              </button>
              <button
                type="button"
                onClick={endTour}
                aria-label="End guided demo"
                className="focus-ring rounded-panel p-0.5 text-ink-500 hover:text-ink-100"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          </div>

          <div className="flex items-start gap-3 px-2.5 py-2.5">
            <span className="bg-accent/12 mt-[1px] flex h-5 w-5 shrink-0 items-center justify-center rounded-panel border border-accent/40 font-mono text-3xs font-bold text-accent">
              {tourStep + 1}
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="text-2xs font-semibold uppercase tracking-[0.08em] text-ink-100">
                {step.title}
              </h3>
              <p className="mt-1 text-2xs leading-relaxed text-ink-300">{step.body}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <Button
                onClick={prevTourStep}
                disabled={tourStep === 0}
                title="Previous demo step"
                aria-label="Previous demo step"
              >
                <ChevronLeft className="h-3 w-3" />
                Back
              </Button>
              <Button variant="primary" onClick={isLast ? endTour : nextTourStep}>
                {isLast ? 'Finish' : 'Next demo step'}
              </Button>
            </div>
          </div>

          <div className="flex gap-[2px] px-2.5 pb-2">
            {STEPS.map((_, index) => (
              <span
                key={index}
                className={cn(
                  'h-[2px] flex-1 rounded-full',
                  index <= tourStep ? 'bg-accent' : 'bg-base-700',
                )}
              />
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

export const DEMO_STEP_COUNT = STEPS.length;
