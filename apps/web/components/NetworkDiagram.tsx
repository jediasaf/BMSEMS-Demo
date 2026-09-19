'use client';

import { cn, num, pct } from '@/lib/format';
import type { NetworkResponse } from '@/lib/types';

/**
 * Single-line diagram, drawn as inline SVG.
 *
 * Deliberately a real SLD rather than a generic node graph: grid symbol,
 * transformer windings with its vector group, a busbar, and feeders whose
 * thickness follows their loading. An electrical engineer should recognise it
 * at a glance.
 */
export function NetworkDiagram({
  network,
  height = 'auto',
  onSelect,
  selected,
}: {
  network: NetworkResponse;
  /** A CSS length. 'auto' sizes from the viewBox, so the drawing fills the
   *  panel's width instead of letterboxing itself inside a fixed box. */
  height?: number | string;
  onSelect?: (id: string) => void;
  selected?: string | null;
}) {
  const { topology, state } = network;
  const feeders = topology.feeders;
  // Wide on purpose: the panel this sits in is far wider than it is tall, and
  // a squarer drawing just letterboxes itself into the middle of it.
  const width = 900;
  const busY = 150;
  const busLeft = 70;
  const busRight = width - 50;
  const spacing = (busRight - busLeft) / Math.max(feeders.length, 1);

  const loadingTone =
    state.transformer_loading_pct >= topology.limits.transformer_critical_pct
      ? '#ff5a5f'
      : state.transformer_loading_pct >= topology.limits.transformer_warn_pct
        ? '#f2b544'
        : '#3ddc97';

  const voltageOk =
    state.min_bus_voltage_pu >= topology.limits.voltage_pu[0]! &&
    state.min_bus_voltage_pu <= topology.limits.voltage_pu[1]!;

  return (
    <svg
      viewBox={`0 0 ${width} 330`}
      style={{ height, width: '100%' }}
      role="img"
      aria-label="Single line diagram of the low-voltage network"
    >
      <defs>
        <linearGradient id="busGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#1fae73" stopOpacity="0.55" />
          <stop offset="50%" stopColor="#3ddc97" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#1fae73" stopOpacity="0.55" />
        </linearGradient>
      </defs>

      {/* Grid supply */}
      <g>
        <circle cx={40} cy={40} r={13} fill="none" stroke="#8ba39f" strokeWidth={1.4} />
        <path d="M31 40 q4.5 -7 9 0 t9 0" fill="none" stroke="#8ba39f" strokeWidth={1.3} />
        <text x={60} y={36} fill="#bdcecb" fontSize={10}>
          Utility grid
        </text>
        <text x={60} y={48} fill="#65807c" fontSize={9} fontFamily="monospace">
          {num(topology.transformer.hv_kv, 0)} kV
        </text>
        <line x1={40} y1={53} x2={40} y2={78} stroke="#2a514c" strokeWidth={1.4} />
      </g>

      {/* Transformer */}
      <g
        onClick={() => onSelect?.('TR-01')}
        style={{ cursor: onSelect ? 'pointer' : 'default' }}
      >
        <circle cx={40} cy={90} r={12} fill="none" stroke={loadingTone} strokeWidth={1.6} />
        <circle cx={40} cy={104} r={12} fill="none" stroke={loadingTone} strokeWidth={1.6} />
        <text x={60} y={90} fill="#e6f0ee" fontSize={10} fontWeight={600}>
          {topology.transformer.id}
        </text>
        <text x={60} y={102} fill="#65807c" fontSize={9} fontFamily="monospace">
          {num(topology.transformer.kva, 0)} kVA · {topology.transformer.vector_group} · vk{' '}
          {num(topology.transformer.vk_percent, 1)}%
        </text>
        <text x={60} y={116} fill={loadingTone} fontSize={13} fontWeight={700} fontFamily="monospace">
          {pct(state.transformer_loading_pct)}
        </text>
        <text x={118} y={116} fill="#65807c" fontSize={9}>
          loading
        </text>
        <line x1={40} y1={116} x2={40} y2={busY} stroke="#2a514c" strokeWidth={1.4} />
        <line x1={40} y1={busY} x2={busLeft} y2={busY} stroke="#2a514c" strokeWidth={1.4} />
      </g>

      {/* Busbar */}
      <g>
        <rect x={busLeft} y={busY - 2.5} width={busRight - busLeft} height={5} fill="url(#busGrad)" rx={1} />
        <text x={busLeft} y={busY - 10} fill="#8ba39f" fontSize={9}>
          LV main busbar · {num(topology.transformer.lv_kv * 1000, 0)} V
        </text>
        <text
          x={busRight}
          y={busY - 10}
          fill={voltageOk ? '#3ddc97' : '#ff5a5f'}
          fontSize={9}
          fontFamily="monospace"
          textAnchor="end"
        >
          {num(state.lv_bus_voltage_pu, 4)} pu
        </text>
      </g>

      {/* Feeders */}
      {feeders.map((feeder, index) => {
        const x = busLeft + spacing * (index + 0.5);
        const kw = state.feeder_load_kw[feeder.id] ?? 0;
        const loading = state.feeder_loading_pct[feeder.id] ?? 0;
        const share = state.total_load_kw > 0 ? kw / state.total_load_kw : 0;
        const strokeWidth = 1.2 + share * 5;
        const colour = feeder.flexible ? '#3ddc97' : '#4cc2ff';
        const isSelected = selected === feeder.id;
        return (
          <g
            key={feeder.id}
            onClick={() => onSelect?.(feeder.id)}
            style={{ cursor: onSelect ? 'pointer' : 'default' }}
          >
            <line
              x1={x}
              y1={busY}
              x2={x}
              y2={busY + 52}
              stroke={colour}
              strokeWidth={strokeWidth}
              strokeOpacity={0.75}
            />
            <rect
              x={x - 42}
              y={busY + 52}
              width={84}
              height={56}
              rx={3}
              fill="#0c1a19"
              stroke={
                isSelected ? '#3ddc97' : feeder.flexible ? 'rgba(61,220,151,0.4)' : '#1e3d39'
              }
              strokeWidth={isSelected ? 1.4 : 1}
            />
            <text x={x} y={busY + 68} fill="#bdcecb" fontSize={9} textAnchor="middle">
              {feeder.id.replace('_', ' ')}
            </text>
            <text
              x={x}
              y={busY + 84}
              fill="#e6f0ee"
              fontSize={13}
              fontWeight={700}
              fontFamily="monospace"
              textAnchor="middle"
            >
              {num(kw, 1)}
            </text>
            <text x={x} y={busY + 96} fill="#65807c" fontSize={8} textAnchor="middle">
              kW · cable {pct(loading, 0)}
            </text>
            <text x={x} y={busY + 122} fill="#65807c" fontSize={8.5} textAnchor="middle">
              {feeder.label}
            </text>
            {feeder.flexible && (
              <text x={x} y={busY + 134} fill="#3ddc97" fontSize={8} textAnchor="middle">
                flexible
              </text>
            )}
          </g>
        );
      })}

      {/* Losses */}
      <text x={busRight} y={busY + 16} fill="#65807c" fontSize={9} textAnchor="end" fontFamily="monospace">
        losses {num(state.losses_kw, 2)} kW
      </text>
    </svg>
  );
}

export function NetworkViolations({ violations }: { violations: string[] }) {
  if (violations.length === 0) {
    return (
      <div className="rounded-panel border border-status-normal/30 bg-status-normal/[0.06] px-2.5 py-1.5 text-2xs text-status-normal">
        No limit violations at this instant. Transformer inside nameplate, all buses inside the
        EN 50160 band. This is the solved present state, not the forward risk above.
      </div>
    );
  }
  return (
    <ul className="space-y-1">
      {violations.map((violation) => (
        <li
          key={violation}
          className={cn(
            'rounded-panel border border-status-critical/40 bg-status-critical/10 px-2.5 py-1.5 text-2xs text-status-critical',
          )}
        >
          {violation}
        </li>
      ))}
    </ul>
  );
}
