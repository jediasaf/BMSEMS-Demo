/** Formatting helpers. One place, so the whole UI rounds the same way. */

import type { Severity, SourceType } from './types';

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}

export function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function kw(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : `${num(value, digits)} kW`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value)
    ? '—'
    : `${num(value, digits)}%`;
}

export function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${num(value, digits)}`;
}

export function clockTime(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

export function dateTime(iso: string): string {
  const date = new Date(iso);
  return `${date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
  })} ${clockTime(iso)}`;
}

export function fullTimestamp(iso: string): string {
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export const SEVERITY_STYLE: Record<Severity, { text: string; bg: string; dot: string; label: string }> =
  {
    INFO: { text: 'text-status-info', bg: 'bg-status-info/10', dot: 'bg-status-info', label: 'Info' },
    LOW: { text: 'text-ink-300', bg: 'bg-base-700/60', dot: 'bg-status-idle', label: 'Low' },
    MEDIUM: {
      text: 'text-status-warning',
      bg: 'bg-status-warning/10',
      dot: 'bg-status-warning',
      label: 'Medium',
    },
    HIGH: {
      text: 'text-status-warning',
      bg: 'bg-status-warning/15',
      dot: 'bg-status-warning',
      label: 'High',
    },
    CRITICAL: {
      text: 'text-status-critical',
      bg: 'bg-status-critical/15',
      dot: 'bg-status-critical',
      label: 'Critical',
    },
  };

export const PROVENANCE_STYLE: Record<
  SourceType,
  { text: string; border: string; bg: string; blurb: string }
> = {
  MEASURED: {
    text: 'text-prov-measured',
    border: 'border-prov-measured/40',
    bg: 'bg-prov-measured/10',
    blurb: 'Read from a published measurement. At most resampled.',
  },
  PREDICTED: {
    text: 'text-prov-predicted',
    border: 'border-prov-predicted/40',
    bg: 'bg-prov-predicted/10',
    blurb: 'Produced by a forecasting model from measured history.',
  },
  SIMULATED: {
    text: 'text-prov-simulated',
    border: 'border-prov-simulated/40',
    bg: 'bg-prov-simulated/10',
    blurb: 'Produced by a physics or network solver. Not an observation.',
  },
  OPTIMISED: {
    text: 'text-prov-optimised',
    border: 'border-prov-optimised/40',
    bg: 'bg-prov-optimised/10',
    blurb: 'A proposed setpoint or dispatch from a constrained optimiser.',
  },
  DERIVED: {
    text: 'text-prov-derived',
    border: 'border-prov-derived/40',
    bg: 'bg-prov-derived/10',
    blurb: 'Computed from measured values plus published metadata.',
  },
  INJECTED: {
    text: 'text-prov-injected',
    border: 'border-prov-injected/40',
    bg: 'bg-prov-injected/10',
    blurb: 'A seeded scenario disturbance added by EcoTwin. Synthetic.',
  },
};

export function loadingTone(pctValue: number): Severity {
  if (pctValue >= 100) return 'CRITICAL';
  if (pctValue >= 85) return 'HIGH';
  if (pctValue >= 70) return 'MEDIUM';
  return 'LOW';
}
