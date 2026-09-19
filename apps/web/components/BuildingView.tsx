'use client';

import { useMemo, useState } from 'react';
import { Box, ChevronDown, ChevronRight, Cpu, Layers, Radio, X } from 'lucide-react';
import { ProvenanceBadge } from './ProvenanceBadge';
import { PROVENANCE_STYLE, cn, num } from '@/lib/format';
import { Field, Pill, StatusDot } from './Primitives';
import type { AssetNode } from '@/lib/types';

/**
 * Building view for **real-data mode**.
 *
 * The source publishes no floor plan and no zone telemetry, so this does not
 * pretend to be one. It shows the hierarchy that can be justified — a building
 * with a measured meter, floors and zones whose load is allocated pro rata by
 * published floor area — and marks every generated node as DERIVED.
 *
 * Zone tiles carrying temperature and occupancy belong in the Control Lab,
 * where a simulator actually produces them.
 */
export function BuildingView({
  root,
  onSelect,
  selected,
}: {
  root: AssetNode;
  onSelect?: (node: AssetNode) => void;
  selected?: string | null;
}) {
  const [mode, setMode] = useState<'tiles' | 'tree'>('tiles');
  const floors = root.children.filter((child) => child.kind === 'floor');
  // `noUncheckedIndexedAccess` makes every metric lookup optional; these are
  // the two the panel is built around, so resolve them once.
  const siteLoadKw = root.metrics.load_kw ?? 0;
  const siteAreaM2 = root.metrics.floor_area_m2 ?? 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-2 flex items-center gap-1.5">
        <SegButton active={mode === 'tiles'} onClick={() => setMode('tiles')}>
          Zones
        </SegButton>
        <SegButton active={mode === 'tree'} onClick={() => setMode('tree')}>
          Hierarchy
        </SegButton>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {mode === 'tiles' ? (
          <div className="space-y-2">
            {/* The one node backed by a measurement. Everything below it is an
                allocation, and the contrast is the point of this panel. */}
            {/* The tile is one big target, but the provenance badge is its own
                control — so the badge sits beside the target rather than
                inside it. A button inside a button is not a thing. */}
            <div
              className={cn(
                'relative rounded-panel border transition-colors',
                selected === root.node_id
                  ? 'border-accent/60 bg-accent/[0.08]'
                  : 'border-prov-derived/35 bg-prov-derived/[0.05] hover:border-prov-derived/55',
              )}
            >
              <button
                type="button"
                onClick={() => onSelect?.(root)}
                aria-label={`Open ${root.name}`}
                className="focus-ring absolute inset-0 rounded-panel"
              />
              <div className="pointer-events-none relative px-2.5 py-2 text-left">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-2xs font-semibold text-ink-100">{root.name}</span>
                  <span className="pointer-events-auto">
                    <ProvenanceBadge provenance={root.provenance} size="xs" align="right" />
                  </span>
                </div>
                <div className="mt-1 flex items-end gap-3">
                  <span className="tabular text-lg font-semibold leading-none text-ink-100">
                    {num(siteLoadKw, 1)}
                    <span className="ml-0.5 text-2xs font-normal text-ink-500">kW</span>
                  </span>
                  <span className="tabular pb-[2px] font-mono text-3xs text-ink-500">
                    {num(siteAreaM2, 0)} m² ·{' '}
                    {num((siteLoadKw / Math.max(siteAreaM2, 1)) * 1000, 1)} W/m²
                  </span>
                  {root.metrics.outdoor_temp_c !== undefined && (
                    <span className="tabular pb-[2px] font-mono text-3xs text-ink-500">
                      {num(root.metrics.outdoor_temp_c, 1)} °C outdoor
                    </span>
                  )}
                </div>
                <div className="mt-1 text-3xs text-ink-600">
                  Whole-site meter · kW derived from the energy counter
                </div>
              </div>
            </div>

            {floors.map((floor) => (
              <div key={floor.node_id}>
                <div className="mb-1 flex items-baseline gap-2">
                  <span className="label">{floor.name}</span>
                  <span className="tabular font-mono text-3xs text-ink-600">
                    {num(floor.metrics.floor_area_m2, 0)} m²
                  </span>
                  <span className="ml-auto text-3xs text-prov-derived/80">pro-rata allocation</span>
                </div>
                <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                  {floor.children.map((zone) => (
                    <ZoneTile
                      key={zone.node_id}
                      zone={zone}
                      siteLoad={siteLoadKw}
                      active={selected === zone.node_id}
                      onClick={() => onSelect?.(zone)}
                    />
                  ))}
                </div>
              </div>
            ))}

            <p className="rounded-panel border border-dashed border-base-600 bg-base-800/40 px-2.5 py-1.5 text-3xs leading-relaxed text-ink-500">
              This source publishes no zone-level telemetry, so zones carry an equal share of the
              metered total by floor area — which is why they read identically. Zone temperature and
              occupancy exist only in the Control Lab, where a simulator produces them.
            </p>
          </div>
        ) : (
          <TreeNode node={root} depth={0} onSelect={onSelect} selected={selected} />
        )}
      </div>
    </div>
  );
}

function ZoneTile({
  zone,
  siteLoad,
  active,
  onClick,
}: {
  zone: AssetNode;
  siteLoad: number;
  active: boolean;
  onClick: () => void;
}) {
  const tone = zone.has_anomaly ? 'warning' : 'normal';
  const allocated = zone.metrics.allocated_load_kw ?? 0;
  const share = siteLoad > 0 ? (allocated / siteLoad) * 100 : 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'focus-ring rounded-panel border px-2 py-1.5 text-left transition-colors',
        active
          ? 'border-accent/60 bg-accent/[0.08]'
          : zone.has_anomaly
            ? 'border-status-warning/40 bg-status-warning/[0.06] hover:border-status-warning/60'
            : 'border-base-600 bg-base-800/60 hover:border-base-500',
      )}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="truncate font-mono text-2xs text-ink-200">{zone.node_id}</span>
        <StatusDot tone={tone} />
      </div>
      <div className="tabular mt-1 text-[13px] font-semibold leading-none text-ink-100">
        {num(allocated, 1)}
        <span className="ml-0.5 text-3xs font-normal text-ink-500">kW</span>
      </div>
      <div className="tabular mt-1 flex items-center justify-between gap-1 font-mono text-3xs text-ink-600">
        <span>{num(zone.metrics.floor_area_m2, 0)} m²</span>
        <span className="text-prov-derived/70">{num(share, 0)}%</span>
      </div>
    </button>
  );
}

const ICONS = {
  site: Box,
  building: Box,
  floor: Layers,
  zone: Box,
  equipment: Cpu,
  point: Radio,
  feeder: Radio,
} as const;

function TreeNode({
  node,
  depth,
  onSelect,
  selected,
}: {
  node: AssetNode;
  depth: number;
  onSelect?: (node: AssetNode) => void;
  selected?: string | null;
}) {
  const [open, setOpen] = useState(depth < 2);
  const Icon = ICONS[node.kind] ?? Box;
  const hasChildren = node.children.length > 0;
  const style = PROVENANCE_STYLE[node.provenance.source_type];

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-1.5 rounded-panel py-[3px] pr-2 transition-colors hover:bg-base-800/70',
          selected === node.node_id && 'bg-accent/[0.08]',
          node.has_anomaly && 'bg-status-warning/[0.05]',
        )}
        style={{ paddingLeft: `${depth * 11 + 4}px` }}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={!hasChildren}
          aria-label={open ? 'Collapse' : 'Expand'}
          className="focus-ring shrink-0 text-ink-600 disabled:opacity-0"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </button>
        <Icon
          className={cn(
            'h-3 w-3 shrink-0',
            node.has_anomaly ? 'text-status-warning' : 'text-ink-600',
          )}
        />
        <button
          type="button"
          onClick={() => onSelect?.(node)}
          className="focus-ring min-w-0 flex-1 truncate text-left text-2xs text-ink-200"
          title={node.detail ?? undefined}
        >
          {node.name}
        </button>
        <span className={cn('shrink-0 font-mono text-3xs opacity-60', style.text)}>
          {node.provenance.source_type.slice(0, 3)}
        </span>
        {Object.entries(node.metrics)
          .slice(0, 1)
          .map(([key, value]) => (
            <span key={key} className="tabular shrink-0 font-mono text-3xs text-ink-500">
              {num(value, key.includes('area') ? 0 : 1)}
              <span className="ml-0.5 text-ink-600">{node.units[key]}</span>
            </span>
          ))}
      </div>
      {open &&
        node.children.map((child) => (
          <TreeNode
            key={child.node_id}
            node={child}
            depth={depth + 1}
            onSelect={onSelect}
            selected={selected}
          />
        ))}
    </div>
  );
}

function SegButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'focus-ring rounded-panel border px-2 py-[3px] text-3xs uppercase tracking-[0.08em] transition-colors',
        active
          ? 'border-accent/40 bg-accent/10 text-accent'
          : 'border-base-600 text-ink-400 hover:text-ink-200',
      )}
    >
      {children}
    </button>
  );
}

/** Right-hand drawer with the detail for a selected asset. */
export function AssetDrawer({ node, onClose }: { node: AssetNode; onClose: () => void }) {
  const style = PROVENANCE_STYLE[node.provenance.source_type];
  const entries = useMemo(() => Object.entries(node.metrics), [node.metrics]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="h-full w-full max-w-sm animate-fade-up overflow-y-auto border-l border-base-600 bg-base-850"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-2 border-b border-base-600 px-3 py-2">
          <div className="min-w-0">
            <div className="label">{node.kind}</div>
            <h2 className="truncate text-xs font-semibold text-ink-100">{node.name}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="focus-ring text-ink-500 hover:text-ink-200"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="space-y-3 p-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill tone="neutral" className={cn(style.border, style.text)} title={style.blurb}>
              {node.provenance.source_type}
            </Pill>
            {node.has_anomaly && <Pill tone="warning">Anomaly in window</Pill>}
          </div>

          {entries.length > 0 && (
            <div className="rounded-panel border border-base-600 bg-base-800/60 p-2.5">
              <div className="label mb-1">Metrics</div>
              {entries.map(([key, value]) => (
                <Field
                  key={key}
                  label={key.replace(/_/g, ' ')}
                  value={`${num(value, key.includes('area') ? 0 : 2)} ${node.units[key] ?? ''}`}
                  mono
                />
              ))}
            </div>
          )}

          {node.detail && (
            <div className="rounded-panel border border-base-600 bg-base-800/60 p-2.5">
              <div className="label mb-1">Note</div>
              <p className="text-2xs leading-relaxed text-ink-300">{node.detail}</p>
            </div>
          )}

          {node.children.length > 0 && (
            <div className="rounded-panel border border-base-600 bg-base-800/60 p-2.5">
              <div className="label mb-1">Contains</div>
              <ul className="space-y-0.5">
                {node.children.map((child) => (
                  <li
                    key={child.node_id}
                    className="flex items-baseline justify-between gap-2 text-2xs"
                  >
                    <span className="truncate text-ink-300">{child.name}</span>
                    <span className="shrink-0 font-mono text-3xs text-ink-600">{child.kind}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
