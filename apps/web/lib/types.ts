/** Wire types. These mirror the Pydantic schemas in `apps/api/schemas`. */

export type SourceType =
  | 'MEASURED'
  | 'PREDICTED'
  | 'SIMULATED'
  | 'OPTIMISED'
  | 'DERIVED'
  | 'INJECTED';

export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface Provenance {
  source_type: SourceType;
  source_key: string;
  source_name: string;
  publisher: string;
  field?: string | null;
  dataset_id?: string | null;
  engine?: string | null;
  engine_label?: string | null;
  model_id?: string | null;
  processing?: string | null;
  units?: string | null;
  timestamp?: string | null;
  quality: string;
  is_fixture: boolean;
  assumptions: string[];
  url?: string | null;
  notes?: string | null;
}

export interface KpiValue {
  key: string;
  label: string;
  value: number | null;
  unit?: string | null;
  display?: string | null;
  delta?: number | null;
  delta_label?: string | null;
  status: Severity;
  provenance: Provenance;
  hint?: string | null;
}

export interface Series {
  series_id: string;
  label: string;
  unit?: string | null;
  timestamps: string[];
  values: (number | null)[];
  lower?: (number | null)[] | null;
  upper?: (number | null)[] | null;
  provenance: Provenance;
}

export interface FeatureContribution {
  feature: string;
  label: string;
  contribution: number;
  direction: 'up' | 'down' | 'flat';
  detail?: string | null;
}

export interface Insight {
  insight_id: string;
  timestamp: string;
  asset_id: string;
  zone_id?: string | null;
  module: 'BMS' | 'EMS';
  kind: string;
  severity: Severity;
  metric: string;
  unit: string;
  observed: number | null;
  expected: number | null;
  deviation: number | null;
  deviation_pct?: number | null;
  robust_z?: number | null;
  threshold?: number | null;
  confidence: number;
  title: string;
  description: string;
  possible_causes: string[];
  recommended_next_step: string;
  provenance: Provenance;
  evidence: FeatureContribution[];
}

export interface ExpectedImpact {
  energy_kwh?: number | null;
  energy_pct?: number | null;
  peak_kw?: number | null;
  peak_pct?: number | null;
  comfort_note?: string | null;
  comfort_violation_kh?: number | null;
  provenance: Provenance;
  basis: string;
}

export interface Recommendation {
  recommendation_id: string;
  timestamp: string;
  asset_id: string;
  zone_id?: string | null;
  module: 'BMS' | 'EMS';
  action: string;
  point: string;
  current_value: number;
  proposed_value: number;
  unit: string;
  rationale: string;
  factors: FeatureContribution[];
  expected_impact?: ExpectedImpact | null;
  confidence: number;
  mode: 'ADVISORY' | 'SIMULATION';
  constraints_checked: string[];
  provenance: Provenance;
  simulatable: boolean;
  source_insight_id?: string | null;
}

export interface AssetNode {
  node_id: string;
  parent_id?: string | null;
  name: string;
  kind: 'site' | 'building' | 'floor' | 'zone' | 'equipment' | 'point' | 'feeder';
  metrics: Record<string, number>;
  units: Record<string, string>;
  status: Severity;
  source_type: SourceType;
  has_anomaly: boolean;
  detail?: string | null;
  children: AssetNode[];
}

export interface SystemStatus {
  data_label: string;
  data_mode: 'REAL_DATA' | 'SAMPLE_FIXTURE';
  data_ok: boolean;
  ai_label: string;
  ai_ok: boolean;
  simulation_label: string;
  simulation_ok: boolean;
  simulation_engine: string;
  interview_mode: boolean;
  demo_mode: boolean;
  source_name: string;
  source_url?: string | null;
  notes: string[];
}

export interface ReplayWindow {
  available: boolean;
  start: string;
  end: string;
  step_minutes: number;
  n_steps: number;
  rule?: string | null;
  speeds: number[];
}

export interface Scenario {
  scenario_id: string;
  module: 'BMS' | 'EMS';
  name: string;
  subtitle: string;
  description: string;
  teaches: string;
  is_baseline: boolean;
  parameters: Record<string, number>;
}

export interface ScenarioInjection {
  scenario_id: string;
  label: string;
  description: string;
  metric: string;
  unit: string;
  peak_injection: number;
  total_injection: number;
  affected_steps: number;
  seed: number;
  detail: Record<string, number>;
}

export interface BmsOverview {
  site_id: string;
  site: { name: string; surface_m2: number };
  scenario_id: string;
  injection: ScenarioInjection | null;
  kpis: KpiValue[];
  timeline: {
    asset_id: string;
    window: { start: string; end: string; step_minutes: number; n_steps: number };
    series: Series[];
    served_by: 'model' | 'seasonal_naive';
    gate_reason: string;
    model_id: string;
  };
  insights: Insight[];
  counts_by_severity: Record<string, number>;
  calibration: {
    published_floor_area_m2: number;
    conditioned_area_m2: number;
    conditioned_share: number;
    method: string;
    bounds: number[];
    time_constants_hours: Record<string, number>;
  };
}

export interface SimKpis {
  energy_kwh: number;
  peak_kw: number;
  comfort_violation_kh: number;
  comfort_violation_steps: number;
  mean_zone_temp_c: number;
  cop_mean: number;
}

export interface ControlLabResult {
  asset_id: string;
  zone_id: string;
  engine: string;
  engine_label: string;
  is_boptest: boolean;
  timestamps: string[];
  baseline: {
    label: string;
    kpis: SimKpis;
    zone_temp_c: number[];
    setpoint_c: number[];
    hvac_kw: number[];
  };
  ai_control: {
    label: string;
    kpis: SimKpis;
    zone_temp_c: number[];
    setpoint_c: number[];
    hvac_kw: number[];
  };
  outdoor_temp_c: number[];
  occupancy: number[];
  delta: Record<string, number>;
  delta_pct: Record<string, number | null>;
  optimisation: {
    status: string;
    solved: boolean;
    solver: string;
    solve_time_s: number;
    constraints: string[];
    notes: string[];
    max_step_change_k: number;
    comfort_slack_kh: number;
  };
  parameters: Record<string, unknown>;
  provenance: Provenance;
  comparison_note: string;
  calibration?: BmsOverview['calibration'];
}

export interface FacilityRow {
  facility_id: string;
  name: string;
  surface_m2: number;
  transformer_kva: number;
  current_demand_kw: number;
  expected_demand_kw: number | null;
  deviation_kw: number | null;
  deviation_pct: number | null;
  predicted_peak_kw: number;
  predicted_peak_at: string;
  predicted_peak_loading_pct: number;
  risk_level: string;
  severity: Severity;
  active_anomalies: number;
  served_by: string;
  model_note: string;
}

export interface Portfolio {
  generated_at: string;
  scenario_id: string;
  kpis: KpiValue[];
  facilities: FacilityRow[];
}

export interface NetworkStateDto {
  converged: boolean;
  total_load_kw: number;
  transformer_loading_pct: number;
  transformer_kva: number;
  lv_bus_voltage_pu: number;
  min_bus_voltage_pu: number;
  losses_kw: number;
  feeder_load_kw: Record<string, number>;
  feeder_loading_pct: Record<string, number>;
  bus_voltages_pu: Record<string, number>;
  line_loading_pct: Record<string, number>;
  status: string;
  violations: string[];
  assumptions: string[];
}

export interface NetworkResponse {
  facility_id: string;
  at: string;
  scenario_id: string;
  topology: {
    facility_id: string;
    transformer: {
      id: string;
      kva: number;
      hv_kv: number;
      lv_kv: number;
      vector_group: string;
      vk_percent: number;
    };
    buses: string[];
    feeders: {
      id: string;
      label: string;
      cable: Record<string, number>;
      flexible: boolean;
    }[];
    limits: {
      voltage_pu: number[];
      transformer_warn_pct: number;
      transformer_critical_pct: number;
    };
  };
  state: NetworkStateDto;
  split: Record<string, number>;
  cap_kw: number;
  provenance: Provenance;
}

export interface RiskResponse {
  facility_id: string;
  assessed_at: string;
  horizon_minutes: number;
  transformer_id: string;
  transformer_kva: number;
  cap_kw: number;
  predicted_peak_kw: number;
  predicted_peak_at: string;
  predicted_peak_loading_pct: number;
  risk_level: string;
  severity: Severity;
  timestamps: string[];
  forecast_kw: number[];
  injected_kw: number[];
  loading_pct: number[];
  contributors: { feeder: string; kw: number; share_pct: number; flexible: boolean }[];
  largest_flexible_contributor: string | null;
  provenance: { forecast: Provenance; loading: Provenance };
  served_by: string;
  gate_reason: string;
}

export interface OptimiseResponse {
  facility_id: string;
  scenario_id: string;
  risk: RiskResponse;
  timestamps: string[];
  baseline_kw: number[];
  optimised_kw: number[];
  hvac_reduction_kw: number[];
  ev_reduction_kw: number[];
  ev_recovery_kw: number[];
  summary: {
    baseline_peak_kw: number;
    optimised_peak_kw: number;
    peak_reduction_kw: number;
    hvac_energy_kwh: number;
    ev_energy_shifted_kwh: number;
    residual_overload_kw: number;
    feasible_within_cap: boolean;
    cap_kw: number;
    target_kw: number;
    status: string;
    solver: string;
    solve_time_s: number;
  };
  constraints: string[];
  notes: string[];
  worst_instant: string;
  network_before: Partial<NetworkStateDto>;
  network_after: Partial<NetworkStateDto>;
  provenance: { optimisation: Provenance; network: Provenance; injection: Provenance | null };
  verification_note: string;
}

export interface CrossModuleChainStep {
  step: string;
  module: 'BMS' | 'EMS';
  detail: string;
  source_type: SourceType;
}

export interface CrossModuleResult {
  available: boolean;
  reason?: string;
  link: {
    facility_id: string;
    risk_level: string;
    predicted_peak_kw: number;
    predicted_peak_loading_pct: number;
    predicted_peak_at: string;
    transformer_id: string;
    contributors: { feeder: string; kw: number; share_pct: number; flexible: boolean }[];
    hvac_contribution_kw: number;
    hvac_share_pct: number;
    building_analysis_available: boolean;
    bms_site_id: string | null;
    call_to_action: string;
  };
  building: {
    engine: string;
    engine_label: string;
    is_boptest: boolean;
    baseline_kpis: SimKpis;
    ai_kpis: SimKpis;
    delta: Record<string, number>;
    delta_pct: Record<string, number | null>;
    optimisation: ControlLabResult['optimisation'];
  };
  hvac_reduction: {
    at_peak_kw: number;
    requested_kw: number;
    clipped: boolean;
    peak_reduction_kw: number;
    mean_reduction_kw: number;
    energy_kwh: number;
    aligned_at: string;
    provenance: Provenance;
  };
  power_impact: {
    instant: string;
    before: Partial<NetworkStateDto>;
    after: Partial<NetworkStateDto>;
    delta_loading_pct: number;
    provenance: Provenance;
  };
  chain: CrossModuleChainStep[];
}

export interface DataQualityResponse {
  asset_id: string;
  report: {
    asset_id: string;
    window_start: string;
    window_end: string;
    expected_samples: number;
    actual_samples: number;
    missing_pct: number;
    duplicate_timestamps: number;
    sampling_minutes: number;
    timezone: string;
    units: Record<string, string>;
    last_timestamp: string | null;
    outlier_count: number;
    outlier_rule: string;
    flatline_runs: number;
    notes: string[];
    source_files: string[];
    extra: Record<string, unknown>;
  };
  source: Record<string, unknown>;
}

export interface ModelCardResponse {
  asset_id: string;
  served_by: 'model' | 'seasonal_naive';
  gate_reason: string;
  model_id: string;
  card: Record<string, unknown> | null;
}
