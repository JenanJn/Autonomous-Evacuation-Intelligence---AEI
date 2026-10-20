/**
 * AEI Mobile — Deterministic Mock / Demo Data
 *
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║  ALL DATA IN THIS FILE IS SIMULATED.                            ║
 * ║  It does NOT represent a real city, real flood event, or real   ║
 * ║  evacuation shelter.  Do not use for real emergency decisions.  ║
 * ╚══════════════════════════════════════════════════════════════════╝
 *
 * The graph topology mirrors the Python backend's synthetic scenario:
 *   A ── B ── C
 *   │    │    │
 *   D ── E ── F
 *
 * Risk scores are the direct_proxy_uncalibrated values from the
 * RandomForest model trained on a 200-row synthetic fixture.
 * They are decision-support proxies, NOT calibrated probabilities.
 */

import type {
  EvacuationPlan,
  RiskOutputRecord,
  RouteResult,
  Shelter,
  AllocationResult,
} from '../types/api';

// ── Zone risk records (from Python demo, seed=2024) ─────────────────────

export const MOCK_ZONE_RISKS: RiskOutputRecord[] = [
  {
    zone_id: 'ZONE_A',
    risk_score: 0.4473,
    risk_category: 'MODERATE',
    data_freshness: 'PT21600S',       // 6 hours old
    risk_status: 'OK',
    contributing_factors: ['FloodProbability_direct_proxy', 'model_version:0.1.0'],
    contract_version: '0.1.0',
    scoring_method: 'direct_proxy_uncalibrated',
  },
  {
    zone_id: 'ZONE_B',
    risk_score: 0.4355,
    risk_category: 'MODERATE',
    data_freshness: 'PT21600S',
    risk_status: 'OK',
    contributing_factors: ['FloodProbability_direct_proxy', 'model_version:0.1.0'],
    contract_version: '0.1.0',
    scoring_method: 'direct_proxy_uncalibrated',
  },
  {
    zone_id: 'ZONE_C',
    risk_score: 0.4600,
    risk_category: 'MODERATE',
    data_freshness: 'PT21600S',
    risk_status: 'OK',
    contributing_factors: ['FloodProbability_direct_proxy', 'model_version:0.1.0'],
    contract_version: '0.1.0',
    scoring_method: 'direct_proxy_uncalibrated',
  },
  {
    zone_id: 'ZONE_D',
    risk_score: 0.4585,
    risk_category: 'MODERATE',
    data_freshness: 'PT21600S',
    risk_status: 'OK',
    contributing_factors: ['FloodProbability_direct_proxy', 'model_version:0.1.0'],
    contract_version: '0.1.0',
    scoring_method: 'direct_proxy_uncalibrated',
  },
  {
    zone_id: 'ZONE_E',
    risk_score: 0.4404,
    risk_category: 'MODERATE',
    data_freshness: 'PT21600S',
    risk_status: 'OK',
    contributing_factors: ['FloodProbability_direct_proxy', 'model_version:0.1.0'],
    contract_version: '0.1.0',
    scoring_method: 'direct_proxy_uncalibrated',
  },
  {
    zone_id: 'ZONE_F',
    risk_score: 0.4299,
    risk_category: 'MODERATE',
    data_freshness: 'PT21600S',
    risk_status: 'OK',
    contributing_factors: ['FloodProbability_direct_proxy', 'model_version:0.1.0'],
    contract_version: '0.1.0',
    scoring_method: 'direct_proxy_uncalibrated',
  },
];

// ── Shelters (SYNTHETIC — not real facilities) ─────────────────────────────

export const MOCK_SHELTERS: Shelter[] = [
  {
    shelter_id: 'SH_C',
    name: 'Evacuation Point C [SIMULATED]',
    lat: 0.0,
    lon: 0.018,
    capacity: 200,
    occupied: 140,
    remaining_capacity: 60,
    status: 'OPEN',
    nearest_node: 'C',
    data_source: 'SYNTHETIC',
    notes: 'Synthetic shelter — not a real evacuation facility.',
  },
  {
    shelter_id: 'SH_F',
    name: 'Evacuation Point F [SIMULATED]',
    lat: -0.005,
    lon: 0.018,
    capacity: 150,
    occupied: 100,
    remaining_capacity: 50,
    status: 'OPEN',
    nearest_node: 'F',
    data_source: 'SYNTHETIC',
    notes: 'Synthetic shelter — not a real evacuation facility.',
  },
];

// ── Primary route A→C (no blockage) ───────────────────────────────────────

export const MOCK_PRIMARY_ROUTE: RouteResult = {
  feasible: true,
  path: ['A', 'B', 'C'],
  edges: [['A', 'B', 0], ['B', 'C', 0]],
  total_length_m: 2400,
  total_cost: 6814,
  total_risk_penalty_m: 4414,
  estimated_travel_time_s: 173,
  mode: 'risk_aware',
  origin: 'A',
  destination: 'C',
  replanned: false,
  notes: [],
};

// ── Replanned route A→C after A-B blockage ────────────────────────────────

export const MOCK_REPLANNED_ROUTE: RouteResult = {
  feasible: true,
  path: ['A', 'D', 'E', 'F', 'C'],
  edges: [['A', 'D', 0], ['D', 'E', 0], ['E', 'F', 0], ['F', 'C', 0]],
  total_length_m: 3600,
  total_cost: 12481,
  total_risk_penalty_m: 8881,
  estimated_travel_time_s: 396,
  mode: 'risk_aware',
  origin: 'A',
  destination: 'C',
  replanned: true,
  notes: [
    'Route replanned after road A→B was blocked.',
    'Alternative path via D→E→F adds 1200 m.',
  ],
};

// ── Allocation ─────────────────────────────────────────────────────────────

const MOCK_ALLOCATION: AllocationResult = {
  assignments: [
    { demand_id: 'ZONE_A', shelter_id: 'SH_C', admitted: 80, requested: 80, route_cost_m: 6814 },
    { demand_id: 'ZONE_B', shelter_id: 'SH_C', admitted: 60, requested: 60, route_cost_m: 3378 },
    { demand_id: 'ZONE_D', shelter_id: 'SH_F', admitted: 100, requested: 100, route_cost_m: 6894 },
  ],
  unassigned: [],
  total_admitted: 240,
  total_requested: 240,
  total_unassigned: 0,
  notes: ['Algorithm: greedy nearest-feasible. NOT guaranteed optimal.'],
};

// ── Full evacuation plan — no blockage ────────────────────────────────────

export const MOCK_PLAN_NORMAL: EvacuationPlan = {
  scenario_id: 'DEMO_SYNTHETIC_001',
  generated_at: '2024-06-01T12:00:00Z',
  is_simulated: true,
  blockage_active: false,
  origin_node: 'A',
  origin_label: 'Demo Origin [SIMULATED]',
  zone_risks: MOCK_ZONE_RISKS,
  primary_route: MOCK_PRIMARY_ROUTE,
  replanned_route: null,
  shelters: MOCK_SHELTERS,
  allocation: MOCK_ALLOCATION,
  warnings: [
    'SIMULATED DATA — not a real emergency scenario.',
    'Risk scores are UNCALIBRATED decision-support proxies.',
    'Travel times are approximate (fixed speed table, no traffic model).',
    'Shelter locations are synthetic — not verified facilities.',
  ],
  contract_version: '0.1.0',
};

// ── Full evacuation plan — with A-B blockage ──────────────────────────────

export const MOCK_PLAN_BLOCKED: EvacuationPlan = {
  ...MOCK_PLAN_NORMAL,
  scenario_id: 'DEMO_SYNTHETIC_001_BLOCKED',
  blockage_active: true,
  primary_route: MOCK_PRIMARY_ROUTE,
  replanned_route: MOCK_REPLANNED_ROUTE,
  warnings: [
    ...MOCK_PLAN_NORMAL.warnings,
    '⚠ Simulated road blockage: A → B is closed. Route has been replanned.',
  ],
};
