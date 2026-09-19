'use client';

import { useState } from 'react';
import { Building2, ChevronDown, ChevronRight, Cpu, Layers, Radio, Square } from 'lucide-react';
import { PROVENANCE_STYLE, cn, num } from '@/lib/format';
import type { AssetNode } from '@/lib/types';

const ICONS = {
  site: Building2,
  building: Building2,
  floor: Layers,
  zone: Square,
  equipment: Cpu,
  point: Radio,
  feeder: Radio,
} as const;

export function AssetTree({ root }: { root: AssetNode }) {
  return (
    <div className="space-y-0.5">
      <TreeNode node={root} depth={0} defaultOpen />
    </div>
  );
}

function TreeNode({
  node,
  depth,
  defaultOpen = false,
}: {
  node: AssetNode;
  depth: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen || depth < 2);
  const Icon = ICONS[node.kind] ?? Square;
  const hasChildren = node.children.length > 0;
  const style = PROVENANCE_STYLE[node.source_type];

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-1.5 rounded-panel py-1 pr-2 transition-colors hover:bg-base-700/50',
          node.has_anomaly && 'bg-status-warning/[0.06]',
        )}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={!hasChildren}
          aria-label={open ? 'Collapse' : 'Expand'}
          className="focus-ring shrink-0 text-ink-500 disabled:opacity-0"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </button>
        <Icon className={cn('h-3 w-3 shrink-0', node.has_anomaly ? 'text-status-warning' : 'text-ink-500')} />
        <span className="min-w-0 flex-1 truncate text-2xs text-ink-200" title={node.detail ?? undefined}>
          {node.name}
        </span>
        <span
          className={cn('shrink-0 font-mono text-[9px] uppercase opacity-0 transition-opacity group-hover:opacity-100', style.text)}
          title={style.blurb}
        >
          {node.source_type}
        </span>
        {Object.entries(node.metrics).slice(0, 2).map(([key, value]) => (
          <span key={key} className="tabular shrink-0 font-mono text-[10px] text-ink-400">
            {num(value, key.includes('area') ? 0 : 1)}
            <span className="ml-0.5 text-ink-600">{node.units[key]}</span>
          </span>
        ))}
      </div>
      {open &&
        node.children.map((child) => (
          <TreeNode key={child.node_id} node={child} depth={depth + 1} />
        ))}
    </div>
  );
}
