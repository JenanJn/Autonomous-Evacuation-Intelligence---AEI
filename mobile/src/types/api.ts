/**
 * AEI Mobile — API Type Definitions
 *
 * These types mirror the Python backend integration contract
 * (integration/schemas.py, CONTRACT_VERSION = "0.1.0").
 *
 * IMPORTANT: risk_score is a SYNTHETIC, PROVISIONAL, UNCALIBRATED
 * decision-support proxy.  It is NOT a calibrated flood probability.
 * Never present it as a probability or a guarantee of safety.
 */

// ── Shared enumerations ────────────────────────────────────────────────────

export type PredictionStatus =
  | 'OK'
  | 'NO_DATA'
  | 'STALE_DATA'
  | 'MODEL_ERROR'
  | 'INVALID_INPUT';

export type RiskStatus =
  | 'OK'
  | 'NO_DATA'
  | 'STALE_DATA'
  | 'SCORING_ERROR'
  | 'INVALID_INPUT';

/**
 * Ordinal risk category.
 * These are DECISION-SUPPORT categories based on configurable thresholds.
 * They are NOT calibrated probabilities.
 * UNKNOWN means data is missing or stale — never treat it as LOW.
 */
export type RiskCategory = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL' | 'UNKNOWN';

export type RoutingMode = 'shortest' | 'risk_aware' | 'adaptive';

export type ShelterStatus = 'OPEN' | 'FULL' | 'CLOSED';

// ── Hazard prediction ──────────────────────────────────────────────────────

export interface HazardPredictionRecord {
  zone_id: string;
  prediction_time: string;           // ISO-8601 UTC
  target_name: string;               // e.g. "FloodProbability"
  predicted_value: number | null;    // null when status != OK
  target_unit: string;               // e.g. "dimensionless_0_to_1"
  forecast_horizon: string;          // e.g. "static_snapshot"
  model_version: string;             // e.g. "0.1.0"
  data_timestamp: string | null;     // ISO-8601 UTC or null
  prediction_status: PredictionStatus;
  contract_version: string;          // "0.1.0"
}

// ── Risk output ────────────────────────────────────────────────────────────

export interface RiskOutputRecord {
  zone_id: string;
  /** Normalised proxy score in [0,1]. null when status != OK. NOT a probability. */
  risk_score: number | null;
  /** Category derived from uncalibrated thresholds (0.25/0.50/0.75). */
  risk_category: RiskCategory;
  /** ISO-8601 duration string e.g. "PT3600S" = 1 hour old. */
  data_freshness: string | null;
  risk_status: RiskStatus;
  contributing_factors: string[];
  contract_version: string;
  /** Added by scoring module — always "direct_proxy_uncalibrated" currently. */
  scoring_method?: string;
}

// ── Routing ────────────────────────────────────────────────────────────────

export interface RouteNode {
  id: string;
  /** Longitude (WGS-84). */
  x: number;
  /** Latitude (WGS-84). */
  y: number;
}

export interface RouteEdge {
  u: string;
  v: string;
  key: number;
  length_m: number;
  road_type: string;
  risk_score: number | null;
  blocked: boolean;
}

export interface RouteResult {
  feasible: boolean;
  path: string[];               // ordered node IDs
  edges: [string, string, number][];
  total_length_m: number;
  total_cost: number;           // metres, includes risk penalty
  total_risk_penalty_m: number;
  /** Approximate; uses fixed speed table — not validated. */
  estimated_travel_time_s: number;
  mode: RoutingMode;
  origin: string;
  destination: string;
  replanned: boolean;
  notes: string[];
}

// ── Shelter ────────────────────────────────────────────────────────────────

export interface Shelter {
  shelter_id: string;
  name: string;
  lat: number;
  lon: number;
  capacity: number;
  occupied: number;
  remaining_capacity: number;
  status: ShelterStatus;
  nearest_node: string | null;
  data_source: string;
  notes: string;
}

export interface ShelterAssignment {
  demand_id: string;
  shelter_id: string;
  admitted: number;
  requested: number;
  route_cost_m: number;
}

export interface AllocationResult {
  assignments: ShelterAssignment[];
  unassigned: Array<{
    demand_id: string;
    requested: number;
    reason: string;
  }>;
  total_admitted: number;
  total_requested: number;
  total_unassigned: number;
  notes: string[];
}

// ── Full evacuation plan (composed response) ──────────────────────────────

export interface EvacuationPlan {
  scenario_id: string;
  generated_at: string;          // ISO-8601 UTC
  /** Whether this plan uses synthetic/demo data. */
  is_simulated: boolean;
  /** True while a road blockage simulation is active. */
  blockage_active: boolean;
  origin_node: string;
  origin_label: string;
  zone_risks: RiskOutputRecord[];
  primary_route: RouteResult;
  /** Populated only when blockage_active=true. */
  replanned_route: RouteResult | null;
  shelters: Shelter[];
  allocation: AllocationResult;
  /** Human-readable warnings. Never empty when risk data is missing or stale. */
  warnings: string[];
  contract_version: string;
}

// ── Location ───────────────────────────────────────────────────────────────

export type LocationMode = 'gps' | 'map' | 'demo';

export interface UserLocation {
  mode: LocationMode;
  lat: number;
  lon: number;
  /** Nearest road-network node ID (resolved server-side or by demo). */
  node_id: string;
  label: string;
}

// ── Connectivity ───────────────────────────────────────────────────────────

export type ConnectivityStatus = 'connected' | 'disconnected' | 'unknown';

export interface ApiHealth {
  status: 'ok' | 'error';
  version: string;
  backend_url: string;
}
