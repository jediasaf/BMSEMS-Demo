'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  Building2,
  ChevronsLeft,
  ChevronsRight,
  CircuitBoard,
  FlaskConical,
  Gauge,
  Info,
  LayoutGrid,
  Presentation,
  Radar,
  SlidersHorizontal,
  Zap,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useDemo } from '@/lib/store';
import { cn } from '@/lib/format';
import { StatusDot } from './Primitives';

const SECTIONS = [
  {
    module: 'BMS' as const,
    label: 'EcoTwin BMS',
    caption: 'AI Building Operator',
    icon: Building2,
    tint: 'text-accent',
    items: [
      { href: '/bms', label: 'Overview', icon: LayoutGrid },
      { href: '/bms/ai-operations', label: 'AI Operations', icon: Radar },
      { href: '/bms/control-lab', label: 'Control Lab', icon: SlidersHorizontal },
    ],
  },
  {
    module: 'EMS' as const,
    label: 'EcoTwin EMS',
    caption: 'AI Power Operator',
    icon: Zap,
    tint: 'text-info',
    items: [
      { href: '/ems', label: 'Portfolio', icon: Gauge },
      { href: '/ems/network', label: 'Power Network', icon: CircuitBoard },
      { href: '/ems/scenario-lab', label: 'Scenario Lab', icon: FlaskConical },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { status, compactNav, toggleCompactNav, interviewMode, setInterviewMode, startTour } =
    useDemo();

  const onReset = async () => {
    try {
      await api.resetDemo();
    } catch {
      /* a failed cache reset is not worth breaking the demo over */
    }
    window.location.reload();
  };

  return (
    <aside
      className={cn(
        'flex shrink-0 flex-col border-r border-base-600/70 bg-base-950/80 transition-[width] duration-200',
        compactNav ? 'w-sidebar-compact' : 'w-sidebar',
      )}
    >
      {/* Wordmark */}
      <Link
        href="/"
        className="focus-ring flex h-topbar shrink-0 items-center gap-2.5 border-b border-base-600/70 px-3"
      >
        <span className="relative flex h-6 w-6 shrink-0 items-center justify-center rounded-panel border border-accent/40 bg-accent/10">
          <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-glow" />
        </span>
        {!compactNav && (
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-[13px] font-semibold tracking-tight text-ink-100">
              EcoTwin AI
            </span>
            <span className="block truncate text-3xs uppercase tracking-[0.1em] text-ink-500">
              Building &amp; Power Ops
            </span>
          </span>
        )}
      </Link>

      <nav className="min-h-0 flex-1 overflow-y-auto py-2">
        {SECTIONS.map((section) => {
          const SectionIcon = section.icon;
          const sectionActive = section.items.some((item) => pathname === item.href);
          return (
            <div key={section.module} className="mb-1.5">
              {!compactNav ? (
                <div className="flex items-center gap-1.5 px-3 pb-1 pt-2">
                  <SectionIcon className={cn('h-3 w-3 shrink-0', section.tint)} />
                  <span className="label truncate">{section.label}</span>
                </div>
              ) : (
                <div className="flex justify-center pb-1 pt-2">
                  <SectionIcon
                    className={cn('h-3.5 w-3.5', sectionActive ? section.tint : 'text-ink-600')}
                  />
                </div>
              )}
              {!compactNav && (
                <div className="px-3 pb-1 text-3xs text-ink-600">{section.caption}</div>
              )}
              <ul>
                {section.items.map((item) => {
                  const Icon = item.icon;
                  const active = pathname === item.href;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        title={compactNav ? item.label : undefined}
                        className={cn(
                          'focus-ring relative flex items-center gap-2.5 py-[7px] text-xs transition-colors',
                          compactNav ? 'justify-center px-0' : 'px-3',
                          active
                            ? 'bg-accent/[0.09] font-medium text-accent'
                            : 'text-ink-300 hover:bg-base-800/70 hover:text-ink-100',
                        )}
                      >
                        {/* Left indicator rather than a pill: keeps the rail flush. */}
                        <span
                          className={cn(
                            'absolute inset-y-0 left-0 w-[2px]',
                            active ? 'bg-accent' : 'bg-transparent',
                          )}
                        />
                        <Icon className="h-3.5 w-3.5 shrink-0" />
                        {!compactNav && <span className="truncate">{item.label}</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      {/* Footer: system status, interview mode, about */}
      <div className="shrink-0 border-t border-base-600/70">
        {!compactNav && status && (
          <div className="space-y-1 px-3 py-2">
            <div className="label">System</div>
            <FooterStat label="Data" value={status.data_label} ok={status.data_ok} />
            <FooterStat label="AI" value={status.ai_label} ok={status.ai_ok} />
            <FooterStat
              label="Sim"
              value={status.simulation_label}
              ok={status.simulation_ok}
              tone={status.simulation_engine === 'BOPTEST' ? 'normal' : 'info'}
            />
          </div>
        )}

        <div className={cn('flex gap-1 px-2 py-2', compactNav && 'flex-col items-center')}>
          <button
            type="button"
            onClick={() => setInterviewMode(!interviewMode)}
            title="Interview mode: curated data, stable scenarios, no experimental surface"
            className={cn(
              'focus-ring flex items-center gap-1.5 rounded-panel border px-1.5 py-1 text-3xs uppercase tracking-[0.08em] transition-colors',
              interviewMode
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-base-600 text-ink-400 hover:text-ink-200',
            )}
          >
            <Presentation className="h-3 w-3 shrink-0" />
            {!compactNav && (interviewMode ? 'Interview' : 'Standard')}
          </button>
          {!compactNav && (
            <button
              type="button"
              onClick={startTour}
              title="Guided walkthrough"
              className="focus-ring flex items-center gap-1.5 rounded-panel border border-base-600 px-1.5 py-1 text-3xs uppercase tracking-[0.08em] text-ink-400 transition-colors hover:text-ink-200"
            >
              <Activity className="h-3 w-3" />
              Demo
            </button>
          )}
        </div>

        <div
          className={cn(
            'flex items-center gap-1 border-t border-base-700/70 px-2 py-1.5',
            compactNav && 'flex-col',
          )}
        >
          <button
            type="button"
            onClick={toggleCompactNav}
            aria-label={compactNav ? 'Expand sidebar' : 'Collapse sidebar'}
            className="focus-ring rounded-panel p-1 text-ink-500 hover:text-ink-200"
          >
            {compactNav ? (
              <ChevronsRight className="h-3.5 w-3.5" />
            ) : (
              <ChevronsLeft className="h-3.5 w-3.5" />
            )}
          </button>
          {!compactNav && (
            <>
              <Link
                href="/about"
                className="focus-ring flex items-center gap-1 rounded-panel p-1 text-3xs uppercase tracking-[0.08em] text-ink-500 hover:text-ink-200"
                title="About and data provenance"
              >
                <Info className="h-3.5 w-3.5" />
                About
              </Link>
              <button
                type="button"
                onClick={onReset}
                className="focus-ring ml-auto text-3xs uppercase tracking-[0.08em] text-ink-500 hover:text-ink-200"
                title="Clear every server-side cache and restore defaults"
              >
                Reset
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

function FooterStat({
  label,
  value,
  ok,
  tone,
}: {
  label: string;
  value: string;
  ok: boolean;
  tone?: 'normal' | 'info';
}) {
  return (
    <div className="flex items-center gap-1.5" title={value}>
      <StatusDot tone={ok ? (tone ?? 'normal') : 'warning'} pulse={ok} />
      <span className="w-6 shrink-0 text-3xs uppercase text-ink-600">{label}</span>
      <span className="truncate text-2xs text-ink-300">{value}</span>
    </div>
  );
}
