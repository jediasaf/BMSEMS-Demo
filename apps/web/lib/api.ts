/**
 * API client.
 *
 * Every call goes through `request`, which enforces a timeout and turns a
 * failure into a typed `ApiError` rather than an unhandled rejection. A demo
 * that blanks out on a slow backend is worse than one that says what went
 * wrong, so callers always have something to render.
 */

import type {
  AssetNode,
  BmsOverview,
  ControlLabResult,
  CrossModuleResult,
  DataQualityResponse,
  Insight,
  ModelCardResponse,
  NetworkResponse,
  OptimiseResponse,
  Portfolio,
  Recommendation,
  ReplayWindow,
  RiskResponse,
  DatasetInfo,
  InterviewPlan,
  PreloadResult,
  Scenario,
  SystemStatus,
} from './types';

/** Where the browser looks for the API, and what "not configured" means.
 *
 * The localhost fallback is a development convenience and a production bug: a
 * deployed build that quietly points at 127.0.0.1 sends every visitor's page
 * to their own machine, so the deployment looks healthy while nothing works.
 * In a production build a missing base is a configuration error, stated as
 * one, rather than a request that can never succeed.
 *
 * Exported as a pure function of its environment so it can be tested without
 * building the app twice.
 */
export function resolveApiBase(env: {
  NEXT_PUBLIC_API_BASE?: string | undefined;
  NODE_ENV?: string | undefined;
}): { base: string; configured: boolean } {
  const configured = env.NEXT_PUBLIC_API_BASE?.trim().replace(/\/+$/, '');
  if (configured) return { base: configured, configured: true };
  if (env.NODE_ENV === 'production') return { base: '', configured: false };
  return { base: 'http://127.0.0.1:8000', configured: true };
}

const resolved = resolveApiBase({
  // Next.js inlines these at build time; they must be referenced literally.
  NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
  NODE_ENV: process.env.NODE_ENV,
});

export const API_BASE = resolved.base;

/** False when a production build shipped without NEXT_PUBLIC_API_BASE. */
export const API_BASE_CONFIGURED = resolved.configured;

export const API_BASE_ERROR =
  'NEXT_PUBLIC_API_BASE is not set in this build. Next.js inlines it at build ' +
  'time, so set it in the deployment environment and redeploy — changing it ' +
  'without rebuilding has no effect.';

const DEFAULT_TIMEOUT_MS = 45_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly path: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

/**
 * Static snapshot mode.
 *
 * The demo is deterministic, so it can be recorded once and served as files
 * from a CDN with no backend at all. `scripts/build_static_snapshot.py` writes
 * one JSON file per request the product can make, keyed by the same path and
 * query this module builds — the two have to agree exactly or the browser asks
 * for a file nobody wrote.
 *
 * This is a replay, and the UI says so. Nothing here fakes liveness: each file
 * carries the provenance it was served with plus a `_snapshot` block naming
 * when it was recorded, and `SNAPSHOT_MODE` drives the banner that tells the
 * viewer they are looking at a recording.
 */
export const SNAPSHOT_MODE = process.env.NEXT_PUBLIC_SNAPSHOT === '1';
const SNAPSHOT_ROOT = '/snapshot';

/** Replay steps are 15 minutes; the recording may keep only every Nth one. */
const SNAPSHOT_STEP_MS = 15 * 60 * 1000;
let snapshotStrideMs = SNAPSHOT_STEP_MS;
let snapshotStart: number | null = null;

/** Told to the client by index.json so `at` can be snapped to a recorded step. */
export function configureSnapshot(start: string | undefined, stride: number | undefined) {
  if (start) snapshotStart = Date.parse(start);
  if (stride && stride > 0) snapshotStrideMs = stride * SNAPSHOT_STEP_MS;
}

export type SnapshotIndex = {
  recorded_at?: string;
  cursor_stride?: number;
  start?: string;
  entries?: number;
};

let snapshotIndex: Promise<SnapshotIndex | null> | null = null;

/** The recording's own description of itself, fetched once and shared.
 *
 * Every request in snapshot mode waits on this, because the cursor cannot be
 * snapped to a recorded step until the stride is known -- and a request made
 * before it lands asks for a file that was never written.
 */
export function snapshotInfo(): Promise<SnapshotIndex | null> {
  if (!snapshotIndex) {
    snapshotIndex = fetch(`${SNAPSHOT_ROOT}/index.json`, {
      headers: { accept: 'application/json' },
    })
      .then((r) => (r.ok ? (r.json() as Promise<SnapshotIndex>) : null))
      .then((index) => {
        if (index) configureSnapshot(index.start, index.cursor_stride);
        return index;
      })
      .catch(() => null);
  }
  return snapshotIndex;
}

/** The nearest recorded cursor at or before `at`, so dragging never 404s. */
function snapCursor(at: string): string {
  const t = Date.parse(at);
  if (snapshotStart === null || Number.isNaN(t)) return at;
  const steps = Math.round((t - snapshotStart) / snapshotStrideMs);
  const snapped = new Date(snapshotStart + Math.max(0, steps) * snapshotStrideMs);
  // The recorder wrote naive local-style stamps, so mirror that format here.
  return snapped.toISOString().slice(0, 19);
}

/** Mirror of `slug()` in scripts/build_static_snapshot.py.
 *
 * Deliberately not URLSearchParams: that percent-encodes the colons in a
 * timestamp, the encoding survives into the filename, and the server then
 * decodes it back before looking the file up — so it is never found. Both
 * sides replace the awkward characters outright instead, and must keep
 * producing byte-identical names.
 */
const snapshotSafe = (text: string) => text.replace(/[^A-Za-z0-9._-]/g, '-');

function snapshotFile(path: string, query?: Query): string {
  const entries = Object.entries(query ?? {})
    .filter(([, v]) => v !== undefined && v !== null && v !== '' && String(v) !== 'None')
    .map(([k, v]) => [k, k === 'at' ? snapCursor(String(v)) : String(v)] as [string, string])
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  const parts = [snapshotSafe(path.replace(/^\//, '').replace(/\//g, '_'))];
  for (const [k, v] of entries) parts.push(`${snapshotSafe(k)}-${snapshotSafe(v)}`);
  return `${SNAPSHOT_ROOT}/${parts.join('__')}.json`;
}

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(
  path: string,
  {
    query,
    method = 'GET',
    timeoutMs = DEFAULT_TIMEOUT_MS,
  }: {
    query?: Query;
    method?: 'GET' | 'POST';
    timeoutMs?: number;
  } = {},
): Promise<T> {
  // Fail loudly and immediately rather than firing a request at an origin
  // that cannot answer. Every caller already renders ApiError.
  // A recording answers every request as a plain file; there is no API base
  // to be missing, so the not-configured check does not apply.
  if (!SNAPSHOT_MODE && !API_BASE_CONFIGURED) throw new ApiError(API_BASE_ERROR, 0, path);
  if (SNAPSHOT_MODE) await snapshotInfo();
  const url = SNAPSHOT_MODE ? snapshotFile(path, query) : `${API_BASE}${withQuery(path, query)}`;
  // The overview's cursor files carry only the KPIs; the timeline, insights
  // and calibration do not move when the cursor does, so they live in one base
  // file per scenario rather than being re-recorded at every step. Merge them
  // back together here so callers see a single ordinary response.
  const mergeBase =
    SNAPSHOT_MODE && path === '/bms/overview' && query?.at
      ? snapshotFile('/bms/overview__base', {
          site_id: query.site_id,
          scenario_id: query.scenario_id,
        })
      : null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      // Files are only ever GET. The live API distinguishes POST for the calls
      // that compute something; the recording of that computation does not.
      method: SNAPSHOT_MODE ? 'GET' : method,
      signal: controller.signal,
      headers: { accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body?.detail) detail = body.detail;
      } catch {
        /* body was not JSON; the status text stands */
      }
      throw new ApiError(detail, response.status, path);
    }
    const body = (await response.json()) as T;
    if (!mergeBase) return body;
    const base = await fetch(mergeBase, { headers: { accept: 'application/json' } });
    if (!base.ok) return body;
    return { ...((await base.json()) as object), ...(body as object) } as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(`Request timed out after ${timeoutMs / 1000}s`, 408, path);
    }
    throw new ApiError(error instanceof Error ? error.message : 'Network error', 0, path);
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  status: () => request<SystemStatus>('/status'),
  replayWindow: () => request<ReplayWindow>('/replay-window'),
  scenarios: (module?: 'BMS' | 'EMS') =>
    request<{ scenarios: Scenario[] }>('/scenarios', { query: { module } }),
  sources: () => request<Record<string, unknown>>('/sources'),
  dataset: () => request<DatasetInfo>('/dataset'),
  resetDemo: () => request<{ reset: boolean; at: string }>('/demo/reset', { method: 'POST' }),

  interview: {
    plan: () => request<InterviewPlan>('/interview/plan'),
    // The preload does every expensive computation the curated path needs, so
    // it is allowed to take longer than an ordinary request.
    preload: () =>
      request<PreloadResult>('/interview/preload', { method: 'POST', timeoutMs: 120_000 }),
    verify: () =>
      request<{
        ready: boolean;
        failed: string[];
        checks: { check: string; passed: boolean; detail: string }[];
      }>('/interview/verify', { timeoutMs: 120_000 }),
  },

  bms: {
    sites: () =>
      request<{ default_site_id: string; sites: Record<string, unknown>[] }>('/bms/sites'),
    overview: (siteId?: string, scenarioId?: string, at?: string) =>
      request<BmsOverview>('/bms/overview', {
        query: { site_id: siteId, scenario_id: scenarioId, at },
      }),
    insights: (siteId?: string, scenarioId?: string) =>
      request<Insight[]>('/bms/insights', {
        query: { site_id: siteId, scenario_id: scenarioId },
      }),
    recommendations: (siteId?: string, scenarioId?: string) =>
      request<Recommendation[]>('/bms/recommendations', {
        query: { site_id: siteId, scenario_id: scenarioId },
      }),
    validate: (recommendationId: string, siteId?: string, scenarioId?: string) =>
      request<{
        valid: boolean;
        mode: string;
        checks: { check: string; passed: boolean; detail: string }[];
        messages: string[];
        note: string;
      }>(`/bms/recommendations/${recommendationId}/validate`, {
        method: 'POST',
        query: { site_id: siteId, scenario_id: scenarioId },
      }),
    assets: (siteId?: string, scenarioId?: string, at?: string) =>
      request<{ root: AssetNode; site_id: string }>('/bms/assets', {
        query: { site_id: siteId, scenario_id: scenarioId, at },
      }),
    controlLab: (siteId?: string, hours = 24, scenarioId?: string) =>
      request<ControlLabResult>('/bms/control-lab', {
        query: { site_id: siteId, hours, scenario_id: scenarioId },
      }),
    modelCard: (siteId?: string) =>
      request<ModelCardResponse>('/bms/model-card', { query: { site_id: siteId } }),
    dataQuality: (siteId?: string) =>
      request<DataQualityResponse>('/bms/data-quality', { query: { site_id: siteId } }),
  },

  ems: {
    facilities: () =>
      request<{ default_facility_id: string; facilities: Record<string, unknown>[] }>(
        '/ems/facilities',
      ),
    portfolio: (scenarioId?: string, at?: string) =>
      request<Portfolio>('/ems/portfolio', { query: { scenario_id: scenarioId, at } }),
    network: (facilityId?: string, scenarioId?: string, at?: string) =>
      request<NetworkResponse>('/ems/network', {
        query: { facility_id: facilityId, scenario_id: scenarioId, at },
      }),
    risk: (facilityId?: string, scenarioId?: string, at?: string) =>
      request<RiskResponse>('/ems/risk', {
        query: { facility_id: facilityId, scenario_id: scenarioId, at },
      }),
    optimise: (facilityId?: string, scenarioId?: string, at?: string) =>
      request<OptimiseResponse>('/ems/optimise', {
        method: 'POST',
        query: { facility_id: facilityId, scenario_id: scenarioId, at },
      }),
    insights: (facilityId?: string, scenarioId?: string) =>
      request<Insight[]>('/ems/insights', {
        query: { facility_id: facilityId, scenario_id: scenarioId },
      }),
    dataQuality: (facilityId?: string) =>
      request<DataQualityResponse>('/ems/data-quality', { query: { facility_id: facilityId } }),
  },

  link: {
    peakToBuilding: (facilityId?: string, scenarioId?: string) =>
      request<CrossModuleResult['link']>('/link/peak-to-building', {
        query: { facility_id: facilityId, scenario_id: scenarioId },
      }),
    simulateHvacAction: (facilityId?: string, scenarioId?: string, hours = 24) =>
      request<CrossModuleResult>('/link/simulate-hvac-action', {
        method: 'POST',
        query: { facility_id: facilityId, scenario_id: scenarioId, hours },
        timeoutMs: 90_000,
      }),
  },
};
