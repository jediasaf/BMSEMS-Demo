'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { X } from 'lucide-react';
import { useDemo } from '@/lib/store';
import { Button } from './Primitives';

interface TourStep {
  title: string;
  body: string;
  href?: string;
  action?: () => void;
}

/**
 * The four-to-six minute walkthrough. Each step navigates and, where useful,
 * sets the scenario — so the demo cannot be knocked off course by a stray click.
 */
export function DemoTour() {
  const router = useRouter();
  const { tourStep, nextTourStep, endTour, setBmsScenario, setEmsScenario, setCursor, window: replayWindow } =
    useDemo();

  const steps: TourStep[] = [
    {
      title: 'EcoTwin BMS — the building as recorded',
      body: 'Real 15-minute metered demand from the Schneider / DrivenData public dataset, with the nearest published weather station. Every number carries a provenance badge: the load is DERIVED because the publisher never states a unit for its energy counter, and outdoor air is MEASURED.',
      href: '/bms',
      action: () => setBmsScenario('bms_normal_day'),
    },
    {
      title: 'Run the historical replay',
      body: 'Press play. The whole platform reads one clock, so the building view and the power view stay on the same instant. The forecast band is a conformalised 80% interval, and the model was trained only on data from before this window.',
      href: '/bms',
    },
    {
      title: 'Inject a hot day and watch detection fire',
      body: 'The disturbance is seeded and additive; the measured series is kept alongside it. The detector scores the forecast residual against an hour-of-day baseline calibrated on history that ends where this window starts — so a fault lasting all window cannot quietly become the new normal.',
      href: '/bms/ai-operations',
      action: () => setBmsScenario('bms_hot_day'),
    },
    {
      title: 'Open the AI recommendation',
      body: 'A constrained setpoint proposal with its contributing factors, the constraints it was checked against, and a safety gate you can run. Note that it claims no saving yet — nothing is asserted before the simulator has run.',
      href: '/bms/ai-operations',
    },
    {
      title: 'Simulate it: baseline versus AI control',
      body: 'The optimiser solves a convex program over a linearised zone model, then the proposal goes back through the full nonlinear simulator. Both columns come from the same engine over identical weather and occupancy, so the delta means something.',
      href: '/bms/control-lab',
    },
    {
      title: 'EcoTwin EMS — the portfolio',
      body: 'The same metered facilities seen as an electrical estate. Transformer ratings are DERIVED from observed peaks by standard sizing practice, because the dataset publishes no nameplate data — and the badge says so.',
      href: '/ems',
      action: () => setEmsScenario('ems_normal_day'),
    },
    {
      title: 'Map the load onto a real network',
      body: 'pandapower solves a balanced AC load flow over a six-bus LV model with catalogue cable impedances. Bus voltages, feeder loading and losses are all SIMULATED and labelled as such.',
      href: '/ems/network',
    },
    {
      title: 'Run the EV charging surge',
      body: 'A seeded 120 kW charging session lands on the flexible feeder. The transformer goes past its nameplate and LV voltage sags. Nothing here is hard-coded — the numbers are a load flow.',
      href: '/ems/scenario-lab',
      action: () => setEmsScenario('ems_ev_surge'),
    },
    {
      title: 'Optimise, then verify',
      body: 'A linear program shifts EV charging and buys HVAC flexibility, with EV energy conserved as a hard equality. The before/after transformer figures are two independent load flows at the worst instant — not the optimiser marking its own homework.',
      href: '/ems/scenario-lab',
    },
    {
      title: 'Close the loop: power risk → building → power impact',
      body: 'The flagship chain. EMS names the flexible contributors, BMS answers with a simulated HVAC action, and EMS re-solves the network with that reduction applied. A thermal simulation feeding an electrical simulation, end to end.',
      href: '/ems/scenario-lab',
    },
    {
      title: 'Measured, predicted, simulated, optimised, injected',
      body: 'Click any provenance badge. Five categories, one closed vocabulary, enforced in the backend: a value cannot be tagged MEASURED unless its registered source is a real measurement, and cannot be tagged SIMULATED without naming the engine that produced it.',
      href: '/bms',
    },
  ];

  const step = tourStep !== null ? steps[tourStep] : undefined;

  useEffect(() => {
    if (!step) return;
    step.action?.();
    if (step.href) router.push(step.href);
  }, [tourStep]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tourStep !== null && replayWindow?.available && tourStep === 1) {
      setCursor(Math.floor(replayWindow.n_steps / 2));
    }
  }, [tourStep, replayWindow, setCursor]);

  if (tourStep === null || !step) return null;
  const isLast = tourStep === steps.length - 1;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center p-3">
      <div className="pointer-events-auto w-full max-w-2xl rounded-panel border border-accent/40 bg-base-850/97 p-3 shadow-2xl backdrop-blur">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-panel bg-accent/15 font-mono text-2xs font-bold text-accent">
            {tourStep + 1}
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-xs font-semibold text-ink-100">{step.title}</h3>
            <p className="mt-1 text-2xs leading-relaxed text-ink-300">{step.body}</p>
          </div>
          <button
            type="button"
            onClick={endTour}
            aria-label="End guided demo"
            className="focus-ring shrink-0 rounded-panel p-1 text-ink-500 hover:text-ink-100"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="mt-2.5 flex items-center gap-2 border-t border-base-700 pt-2.5">
          <div className="flex flex-1 gap-1">
            {steps.map((_, index) => (
              <span
                key={index}
                className={`h-0.5 flex-1 rounded-full ${
                  index <= tourStep ? 'bg-accent' : 'bg-base-600'
                }`}
              />
            ))}
          </div>
          <span className="tabular shrink-0 font-mono text-[10px] text-ink-500">
            {tourStep + 1}/{steps.length}
          </span>
          <Button size="sm" variant="primary" onClick={isLast ? endTour : nextTourStep}>
            {isLast ? 'Finish' : 'Next'}
          </Button>
        </div>
      </div>
    </div>
  );
}
