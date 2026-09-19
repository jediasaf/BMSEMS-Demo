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
  Scenario,
  SystemStatus,
} from './types';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000';

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
  { query, method = 'GET', timeoutMs = DEFAULT_TIMEOUT_MS }: {
    query?: Query;
    method?: 'GET' | 'POST';
    timeoutMs?: number;
  } = {},
): Promise<T> {
  const url = `${API_BASE}${withQuery(path, query)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method,
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
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(`Request timed out after ${timeoutMs / 1000}s`, 408, path);
    }
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error',
      0,
      path,
    );
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
