'use client';

import { create } from 'zustand';
import type { ReplayWindow, Scenario, SystemStatus } from './types';

/**
 * Shared demo state.
 *
 * The replay clock lives here rather than in a page, because both modules
 * animate against the same instant — that is what makes the BMS↔EMS link feel
 * like one system instead of two tabs.
 */

interface DemoState {
  status: SystemStatus | null;
  window: ReplayWindow | null;
  scenarios: Scenario[];
  bmsScenario: string;
  emsScenario: string;
  siteId: string | null;
  facilityId: string | null;
  /** Index into the replay window, in 15-minute steps. */
  cursor: number;
  playing: boolean;
  speed: number;
  interviewMode: boolean;
  tourStep: number | null;
  /** Result of the last Interview Mode preload, for the system bar. */
  preload: PreloadState;
  compactNav: boolean;
  /**
   * Bumped by `resetDemo`. Pages hold their own simulation and optimisation
   * results in local state; watching this is how they know to drop them, so a
   * reset really does return the whole product to its opening position rather
   * than only the parts the store happens to own.
   */
  resetToken: number;
  /** Asset selected in the BMS building view, shown in the detail drawer. */
  selectedZone: string | null;
  /** Insight selected in the AI Operations feed. */
  selectedInsight: string | null;

  setStatus: (status: SystemStatus) => void;
  setWindow: (window: ReplayWindow) => void;
  setScenarios: (scenarios: Scenario[]) => void;
  setBmsScenario: (id: string) => void;
  setEmsScenario: (id: string) => void;
  setSiteId: (id: string) => void;
  setFacilityId: (id: string) => void;
  setCursor: (cursor: number) => void;
  tick: () => void;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  setSpeed: (speed: number) => void;
  setInterviewMode: (on: boolean) => void;
  setPreload: (preload: PreloadState) => void;
  toggleCompactNav: () => void;
  setSelectedZone: (id: string | null) => void;
  setSelectedInsight: (id: string | null) => void;
  startTour: () => void;
  nextTourStep: () => void;
  prevTourStep: () => void;
  goToTourStep: (step: number) => void;
  endTour: () => void;
  resetDemo: () => void;
}

export type PreloadState =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'ready'; ms: number }
  | { state: 'failed'; failed: string[] };

/** The opening position, in one place, so reset and start agree on it. */
const OPENING = {
  bmsScenario: 'bms_normal_day',
  emsScenario: 'ems_normal_day',
  playing: false,
  speed: 20,
  tourStep: null,
  selectedZone: null,
  selectedInsight: null,
} as const;

export const useDemo = create<DemoState>((set, get) => ({
  status: null,
  window: null,
  scenarios: [],
  bmsScenario: 'bms_normal_day',
  emsScenario: 'ems_normal_day',
  siteId: null,
  facilityId: null,
  cursor: 0,
  playing: false,
  speed: 20,
  interviewMode: true,
  tourStep: null,
  preload: { state: 'idle' },
  compactNav: false,
  resetToken: 0,
  selectedZone: null,
  selectedInsight: null,

  setStatus: (status) => set({ status, interviewMode: status.interview_mode }),
  setWindow: (window) => set({ window, cursor: openingCursor(window) }),
  setScenarios: (scenarios) => set({ scenarios }),
  setBmsScenario: (bmsScenario) => set({ bmsScenario }),
  setEmsScenario: (emsScenario) => set({ emsScenario }),
  setSiteId: (siteId) => set({ siteId }),
  setFacilityId: (facilityId) => set({ facilityId }),
  setCursor: (cursor) => set({ cursor: Math.max(0, cursor) }),
  tick: () => {
    const { cursor, window } = get();
    if (!window) return;
    const next = cursor + 1;
    set({ cursor: next >= window.n_steps ? 0 : next });
  },
  play: () => set({ playing: true }),
  pause: () => set({ playing: false }),
  toggle: () => set({ playing: !get().playing }),
  setSpeed: (speed) => set({ speed }),
  setInterviewMode: (interviewMode) => set({ interviewMode }),
  setPreload: (preload) => set({ preload }),
  toggleCompactNav: () => set({ compactNav: !get().compactNav }),
  setSelectedZone: (selectedZone) => set({ selectedZone }),
  setSelectedInsight: (selectedInsight) => set({ selectedInsight }),
  startTour: () => set({ tourStep: 0 }),
  nextTourStep: () => set({ tourStep: (get().tourStep ?? 0) + 1 }),
  prevTourStep: () => set({ tourStep: Math.max((get().tourStep ?? 0) - 1, 0) }),
  goToTourStep: (tourStep) => set({ tourStep: Math.max(tourStep, 0) }),
  endTour: () => set({ tourStep: null }),
  resetDemo: () =>
    set((state) => ({
      ...OPENING,
      cursor: openingCursor(state.window),
      resetToken: state.resetToken + 1,
    })),
}));

/**
 * Where the replay opens: the second morning of the window, so the forward
 * risk horizon covers an afternoon peak rather than a quiet midnight. Anchored
 * to the window rather than to wall-clock time, which is what makes two runs
 * of the demo land on the same instant.
 */
export function openingCursor(window: ReplayWindow | null): number {
  if (!window?.available) return 0;
  return Math.min(Math.floor(window.n_steps / 2), Math.max(window.n_steps - 1, 0));
}

/**
 * The timestamp the replay cursor points at, in the dataset's own clock.
 *
 * Deliberately *not* `toISOString()`. The source publishes no UTC offset, so
 * the backend works in a naive local clock; serialising as UTC would shift the
 * cursor by the viewer's timezone — a bug that looks like it worked.
 */
export function cursorTimestamp(window: ReplayWindow | null, cursor: number): string | null {
  if (!window?.available) return null;
  const start = new Date(window.start).getTime();
  const at = new Date(start + cursor * window.step_minutes * 60_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}` +
    `T${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`
  );
}
