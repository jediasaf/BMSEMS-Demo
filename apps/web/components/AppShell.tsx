'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { Building2, Zap } from 'lucide-react';
import { api } from '@/lib/api';
import { useDemo } from '@/lib/store';
import { cn } from '@/lib/format';
import { StatusBar } from './StatusBar';
import { DemoTour } from './DemoTour';

const NAV = [
  {
    module: 'BMS' as const,
    icon: Building2,
    label: 'EcoTwin BMS',
    subtitle: 'AI Building Operator',
    items: [
      { href: '/bms', label: 'Overview' },
      { href: '/bms/ai-operations', label: 'AI Operations' },
      { href: '/bms/control-lab', label: 'Control Lab' },
    ],
  },
  {
    module: 'EMS' as const,
    icon: Zap,
    label: 'EcoTwin EMS',
    subtitle: 'AI Power Operator',
    items: [
      { href: '/ems', label: 'Portfolio' },
      { href: '/ems/network', label: 'Power Network' },
      { href: '/ems/scenario-lab', label: 'Scenario Lab' },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { setWindow, setScenarios, startTour } = useDemo();
  const isEms = pathname.startsWith('/ems');

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
    <div className="flex min-h-screen flex-col">
      <StatusBar />

      <header className="flex h-12 shrink-0 items-center gap-4 border-b border-base-600/70 bg-base-850/70 px-3 backdrop-blur">
        <Link href="/" className="focus-ring flex shrink-0 items-center gap-2">
          <span className="relative flex h-6 w-6 items-center justify-center rounded-panel bg-accent/15 shadow-glow">
            <span className="h-2 w-2 rounded-full bg-accent" />
          </span>
          <span className="leading-tight">
            <span className="block text-xs font-semibold tracking-tight text-ink-100">
              EcoTwin AI
            </span>
            <span className="block text-[10px] text-ink-500">
              AI Building &amp; Power Operations
            </span>
          </span>
        </Link>

        <nav className="flex items-stretch gap-1">
          {NAV.map((group) => {
            const groupActive = group.items.some((item) => pathname === item.href) ||
              (group.module === 'EMS' ? isEms : pathname.startsWith('/bms'));
            const Icon = group.icon;
            return (
              <div
                key={group.module}
                className={cn(
                  'flex items-center gap-1 rounded-panel border px-1.5 py-1 transition-colors',
                  groupActive
                    ? 'border-base-500 bg-base-800/80'
                    : 'border-transparent opacity-60 hover:opacity-100',
                )}
              >
                <span className="flex items-center gap-1.5 pl-0.5 pr-1">
                  <Icon
                    className={cn(
                      'h-3.5 w-3.5',
                      group.module === 'BMS' ? 'text-teal' : 'text-accent',
                    )}
                  />
                  <span className="hidden leading-none lg:block">
                    <span className="block text-[11px] font-semibold text-ink-100">
                      {group.label}
                    </span>
                    <span className="block text-[9px] text-ink-500">{group.subtitle}</span>
                  </span>
                </span>
                {group.items.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      'focus-ring rounded-pill px-2 py-1 text-2xs font-medium transition-colors',
                      pathname === item.href
                        ? 'bg-accent/15 text-accent'
                        : 'text-ink-400 hover:bg-base-700 hover:text-ink-100',
                    )}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>

        <button
          type="button"
          onClick={startTour}
          className="focus-ring ml-auto rounded-panel border border-base-500 px-2 py-1 text-2xs text-ink-300 transition-colors hover:border-accent/50 hover:text-accent"
        >
          Guided demo
        </button>
      </header>

      <main className="min-w-0 flex-1 p-3">{children}</main>

      <footer className="shrink-0 border-t border-base-600/70 bg-base-850/60 px-3 py-1.5">
        <p className="text-[10px] leading-relaxed text-ink-500">
          Not an official Schneider Electric product. EcoStruxure-ready architecture, designed for
          future integration with EcoStruxure Building Operation and EcoStruxure Power Monitoring
          Expert. This prototype does not connect to a live Schneider Electric customer
          environment; public Schneider data are used for analytics and all control experiments run
          in simulation.
        </p>
      </footer>

      <DemoTour />
    </div>
  );
}
