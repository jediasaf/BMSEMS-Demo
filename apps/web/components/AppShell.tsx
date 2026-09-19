'use client';

import { useEffect } from 'react';
import { api } from '@/lib/api';
import { useDemo } from '@/lib/store';
import { Sidebar } from './Sidebar';
import { SystemBar } from './SystemBar';
import { DemoTour } from './DemoTour';

/**
 * Shell: system bar across the top, fixed sidebar, scrolling workspace.
 *
 * The workspace scrolls rather than the page, so the sidebar and system bar
 * never leave the screen — the operational context is always readable.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { setWindow, setScenarios } = useDemo();

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.replayWindow(), api.scenarios()])
      .then(([window, scenarios]) => {
        if (cancelled) return;
        setWindow(window);
        setScenarios(scenarios.scenarios);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [setWindow, setScenarios]);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <SystemBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
      <DemoTour />
    </div>
  );
}

/** Scrolling region beneath a PageHeader. */
export function Workspace({ children }: { children: React.ReactNode }) {
  return <div className="min-h-0 flex-1 overflow-y-auto p-2.5">{children}</div>;
}
