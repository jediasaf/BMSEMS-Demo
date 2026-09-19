'use client';

import { useState } from 'react';
import { Brain, X } from 'lucide-react';
import { api } from '@/lib/api';
import { useAsync } from '@/lib/useAsync';
import { num } from '@/lib/format';
import { Button, ErrorNote, Pill, Skeleton } from '@/components/Primitives';

interface SplitMetrics {
  label: string;
  n: number;
  start: string;
  end: string;
  mae_kw: number;
  rmse_kw: number;
  wape_pct: number;
  r2: number;
  baseline_mae_kw: number;
  baseline_name: string;
  skill_vs_baseline_pct: number;
  interval_coverage_pct: number;
  raw_interval_coverage_pct: number;
  interval_target_pct: number;
  mean_interval_width_kw: number;
}

interface Card {
  model_id: string;
  family: string;
  trained_at: string;
  training_cutoff: string | null;
  n_features: number;
  metrics: {
    n_train: number;
    n_calib: number;
    train_start: string;
    train_end: string;
    conformal_offset_kw: number;
    backtest: SplitMetrics;
    live: SplitMetrics | null;
  };
  top_features: { feature: string; label: string; importance: number }[];
  notes: string[];
  interval_method: string;
  leakage_control: string;
}

export function ModelExplanationDrawer({ siteId }: { siteId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Brain className="h-3 w-3" />
        Model card
      </Button>
      {open && <Drawer siteId={siteId} onClose={() => setOpen(false)} />}
    </>
  );
}

function Drawer({ siteId, onClose }: { siteId: string; onClose: () => void }) {
  const { data, error, loading, reload } = useAsync(() => api.bms.modelCard(siteId), [siteId]);
  const card = data?.card as unknown as Card | null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="h-full w-full max-w-lg overflow-y-auto border-l border-base-600 bg-base-850 p-4"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-base-600 pb-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-200">
            Forecast model — asset {siteId}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="focus-ring text-ink-400 hover:text-ink-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {loading && !data && <Skeleton className="mt-3 h-64 w-full" />}
        {error && (
          <div className="mt-3">
            <ErrorNote message={error} onRetry={reload} />
          </div>
        )}

        {data && (
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={data.served_by === 'model' ? 'accent' : 'warning'}>
                serving: {data.served_by === 'model' ? 'LightGBM' : 'seasonal naive'}
              </Pill>
              <span className="font-mono text-[10px] text-ink-400">{data.model_id}</span>
            </div>
            <p className="rounded-panel border border-base-600 bg-base-800/60 p-2.5 text-2xs leading-relaxed text-ink-300">
              {data.gate_reason}
            </p>

            {card && (
              <>
                <Section title="Evaluation">
                  <p className="mb-2 text-[10px] leading-relaxed text-ink-500">
                    Backtest is a chronological holdout inside the training history — large enough
                    for the numbers to mean something. Live is the window the demo replays, held out
                    entirely by the training cutoff.
                  </p>
                  <MetricsTable backtest={card.metrics.backtest} live={card.metrics.live} />
                </Section>

                <Section title="Prediction interval">
                  <p className="text-2xs leading-relaxed text-ink-300">{card.interval_method}</p>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    <Stat
                      label="Target"
                      value={`${num(card.metrics.backtest.interval_target_pct, 0)}%`}
                    />
                    <Stat
                      label="Raw"
                      value={`${num(card.metrics.backtest.raw_interval_coverage_pct, 1)}%`}
                    />
                    <Stat
                      label="Conformalised"
                      value={`${num(card.metrics.backtest.interval_coverage_pct, 1)}%`}
                      accent
                    />
                  </div>
                  <p className="mt-1.5 text-[10px] text-ink-500">
                    Conformal offset {num(card.metrics.conformal_offset_kw, 2)} kW.
                  </p>
                </Section>

                <Section title="Top features by gain">
                  <ul className="space-y-1.5">
                    {card.top_features.slice(0, 8).map((feature) => (
                      <li key={feature.feature}>
                        <div className="flex items-baseline justify-between gap-2 text-2xs">
                          <span className="truncate text-ink-300">{feature.label}</span>
                          <span className="tabular shrink-0 font-mono text-ink-100">
                            {num(feature.importance * 100, 1)}%
                          </span>
                        </div>
                        <div className="mt-0.5 h-0.5 w-full overflow-hidden rounded-full bg-base-700">
                          <div
                            className="h-full bg-status-info"
                            style={{ width: `${Math.min(feature.importance * 100, 100)}%` }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 border-t border-base-700 pt-2 text-[10px] leading-relaxed text-ink-500">
                    Gain-based importance describes what the model used. It is not evidence of
                    cause.
                  </p>
                </Section>

                <Section title="Leakage control">
                  <p className="text-2xs leading-relaxed text-ink-300">{card.leakage_control}</p>
                  <dl className="mt-2 space-y-0.5 text-[10px]">
                    <Row label="Trained" value={card.trained_at} />
                    <Row label="Cutoff" value={card.training_cutoff ?? 'none'} />
                    <Row label="Fit rows" value={num(card.metrics.n_train, 0)} />
                    <Row label="Calibration rows" value={num(card.metrics.n_calib, 0)} />
                    <Row label="Features" value={num(card.n_features, 0)} />
                  </dl>
                </Section>

                {card.notes.length > 0 && (
                  <Section title="Notes">
                    <ul className="space-y-1">
                      {card.notes.map((note) => (
                        <li
                          key={note}
                          className="flex gap-1.5 text-2xs leading-relaxed text-ink-300"
                        >
                          <span className="text-ink-600">·</span>
                          <span>{note}</span>
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}
              </>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function MetricsTable({ backtest, live }: { backtest: SplitMetrics; live: SplitMetrics | null }) {
  const rows: { label: string; a: string; b: string }[] = [
    { label: 'Samples', a: num(backtest.n, 0), b: live ? num(live.n, 0) : '—' },
    { label: 'MAE (kW)', a: num(backtest.mae_kw, 2), b: live ? num(live.mae_kw, 2) : '—' },
    {
      label: 'WAPE',
      a: `${num(backtest.wape_pct, 1)}%`,
      b: live ? `${num(live.wape_pct, 1)}%` : '—',
    },
    { label: 'R²', a: num(backtest.r2, 3), b: live ? num(live.r2, 3) : '—' },
    {
      label: `Skill vs ${backtest.baseline_name}`,
      a: `${num(backtest.skill_vs_baseline_pct, 1)}%`,
      b: live ? `${num(live.skill_vs_baseline_pct, 1)}%` : '—',
    },
    {
      label: 'Interval coverage',
      a: `${num(backtest.interval_coverage_pct, 1)}%`,
      b: live ? `${num(live.interval_coverage_pct, 1)}%` : '—',
    },
  ];
  return (
    <div className="overflow-hidden rounded-panel border border-base-600">
      <div className="grid grid-cols-[1.3fr_1fr_1fr] border-b border-base-600 bg-base-800/80 px-2 py-1">
        <span className="text-[10px] uppercase tracking-wider text-ink-500">Metric</span>
        <span className="text-right text-[10px] uppercase tracking-wider text-ink-400">
          Backtest
        </span>
        <span className="text-right text-[10px] uppercase tracking-wider text-accent">Live</span>
      </div>
      {rows.map((row) => (
        <div
          key={row.label}
          className="grid grid-cols-[1.3fr_1fr_1fr] border-b border-base-700/60 px-2 py-1 last:border-b-0"
        >
          <span className="truncate text-2xs text-ink-300">{row.label}</span>
          <span className="tabular text-right text-2xs text-ink-200">{row.a}</span>
          <span className="tabular text-right text-2xs font-medium text-ink-100">{row.b}</span>
        </div>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-panel border border-base-600 bg-base-800/60 p-2.5">
      <h3 className="text-[10px] uppercase tracking-wider text-ink-500">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-500">{label}</div>
      <div className={`tabular text-sm font-semibold ${accent ? 'text-accent' : 'text-ink-100'}`}>
        {value}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-ink-500">{label}</dt>
      <dd className="truncate font-mono text-ink-200">{value}</dd>
    </div>
  );
}
