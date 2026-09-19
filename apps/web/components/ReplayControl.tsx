'use client';

import { useEffect, useRef } from 'react';
import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import { cursorTimestamp, useDemo } from '@/lib/store';
import { cn, fullTimestamp } from '@/lib/format';

/**
 * Historical replay transport.
 *
 * The clock advances one 15-minute step per tick; speed multiplies the tick
 * rate. Nothing here fakes progress — the cursor indexes real samples in the
 * replay window, and every panel reads the same cursor.
 */
export function ReplayControl({ compact = false }: { compact?: boolean }) {
  const {
    window: replayWindow,
    cursor,
    setCursor,
    playing,
    toggle,
    speed,
    setSpeed,
    tick,
  } = useDemo();
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!playing || !replayWindow?.available) return;
    // 1x advances one 15-minute step every 2 s; 60x is a step every ~33 ms.
    timer.current = setInterval(tick, Math.max(2000 / speed, 33));
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, speed, tick, replayWindow?.available]);

  if (!replayWindow?.available) {
    return <div className="text-3xs text-ink-600">Replay window unavailable</div>;
  }

  const stamp = cursorTimestamp(replayWindow, cursor);
  const progress = (cursor / Math.max(replayWindow.n_steps - 1, 1)) * 100;

  return (
    <div className={cn('flex items-center gap-2', compact ? 'text-3xs' : 'text-2xs')}>
      <div className="flex items-center gap-0.5">
        <TransportButton
          label="Step back"
          onClick={() => setCursor(Math.max(cursor - 4, 0))}
          icon={<SkipBack className="h-3 w-3" />}
        />
        <button
          type="button"
          onClick={toggle}
          aria-label={playing ? 'Pause replay' : 'Play replay'}
          className={cn(
            'focus-ring flex h-[22px] w-[22px] items-center justify-center rounded-panel border transition-colors',
            playing
              ? 'border-accent/60 bg-accent/15 text-accent'
              : 'border-base-500 bg-base-750 text-ink-200 hover:border-base-400',
          )}
        >
          {playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
        </button>
        <TransportButton
          label="Step forward"
          onClick={() => setCursor(Math.min(cursor + 4, replayWindow.n_steps - 1))}
          icon={<SkipForward className="h-3 w-3" />}
        />
      </div>

      <div className="tabular shrink-0 font-mono text-2xs text-ink-100">
        {stamp ? fullTimestamp(stamp) : '—'}
      </div>

      <div className="relative min-w-[6rem] flex-1">
        <input
          type="range"
          min={0}
          max={replayWindow.n_steps - 1}
          value={cursor}
          onChange={(event) => setCursor(Number(event.target.value))}
          aria-label="Replay position"
          className="focus-ring h-[3px] w-full cursor-pointer appearance-none rounded-full accent-accent"
          style={{
            background: `linear-gradient(to right, #3ddc97 ${progress}%, #1e3d39 ${progress}%)`,
          }}
        />
      </div>

      <div className="flex shrink-0 items-center gap-0.5">
        {replayWindow.speeds.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setSpeed(value)}
            className={cn(
              'focus-ring rounded-pill px-1.5 py-[1px] font-mono text-3xs transition-colors',
              speed === value
                ? 'bg-accent/15 text-accent'
                : 'text-ink-500 hover:bg-base-750 hover:text-ink-200',
            )}
          >
            {value}x
          </button>
        ))}
      </div>
    </div>
  );
}

function TransportButton({
  label,
  onClick,
  icon,
}: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="focus-ring flex h-[22px] w-[22px] items-center justify-center rounded-panel border border-base-500 bg-base-750 text-ink-400 transition-colors hover:border-base-400 hover:text-ink-100"
    >
      {icon}
    </button>
  );
}
