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
  startTour: () => void;
  nextTourStep: () => void;
  endTour: () => void;
  reset: () => void;
}

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

  setStatus: (status) => set({ status, interviewMode: status.interview_mode }),
  setWindow: (window) =>
    set({
      window,
      // Open on the second morning: the forward risk horizon then covers a real
      // afternoon peak rather than a quiet midnight.
      cursor: Math.min(Math.floor(window.n_steps / 2), Math.max(window.n_steps - 1, 0)),
    }),
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
  startTour: () => set({ tourStep: 0 }),
  nextTourStep: () => set({ tourStep: (get().tourStep ?? 0) + 1 }),
  endTour: () => set({ tourStep: null }),
  reset: () =>
    set({
      bmsScenario: 'bms_normal_day',
      emsScenario: 'ems_normal_day',
      cursor: get().window ? Math.floor(get().window!.n_steps / 2) : 0,
      playing: false,
      speed: 20,
      tourStep: null,
    }),
}));

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
