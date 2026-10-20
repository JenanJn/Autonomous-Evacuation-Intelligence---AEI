/**
 * AEI Mobile — API Client
 *
 * Clean abstraction layer between the screens and the data source.
 * In Demo Mode every function returns mock data immediately.
 * When a real FastAPI backend is available, set BACKEND_URL and
 * call the real endpoints instead — the function signatures stay the same.
 *
 * The mobile app MUST NOT modify anything in the Python backend (api/ or AEI/).
 */

import {
  MOCK_PLAN_NORMAL,
  MOCK_PLAN_BLOCKED,
} from '../data/mockData';
import type {
  ApiHealth,
  ConnectivityStatus,
  EvacuationPlan,
  UserLocation,
} from '../types/api';

// ── Configuration ──────────────────────────────────────────────────────────

/**
 * Set this to the real FastAPI server URL when deploying against the backend.
 * Leave empty to use Demo Mode only.
 */
const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL ?? '';

const REQUEST_TIMEOUT_MS = 8_000;
let demoAnchor: UserLocation | null = null;
function anchoredDemo(blocked = false): EvacuationPlan {
  const plan: EvacuationPlan = JSON.parse(JSON.stringify(blocked ? MOCK_PLAN_BLOCKED : MOCK_PLAN_NORMAL));
  if (demoAnchor) {
    const c = Math.max(0.1, Math.cos(demoAnchor.lat * Math.PI / 180));
    plan.shelters = plan.shelters.map(s => ({ ...s, lat: demoAnchor!.lat + s.lat, lon: demoAnchor!.lon + s.lon / c }));
    plan.origin_label = `SIMULATED disaster at ${demoAnchor.label}`;
    plan.generated_at = new Date().toISOString();
    plan.warnings = [...plan.warnings, 'Training scenario anchored to your location. Shelters and roads are simulated, not verified local infrastructure.'];
  }
  return plan;
}

// ── Internal helpers ───────────────────────────────────────────────────────

async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(id);
  }
}

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * Check whether the Python backend is reachable.
 * Returns 'disconnected' immediately in Demo Mode (no BACKEND_URL).
 */
export async function checkHealth(): Promise<ApiHealth> {
  if (!BACKEND_URL) {
    return {
      status: 'error',
      version: 'demo',
      backend_url: '(not configured)',
    };
  }
  try {
    const res = await fetchWithTimeout(`${BACKEND_URL}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json() as ApiHealth;
    return data;
  } catch {
    return {
      status: 'error',
      version: 'unknown',
      backend_url: BACKEND_URL,
    };
  }
}

export async function getConnectivityStatus(): Promise<ConnectivityStatus> {
  if (!BACKEND_URL) return 'disconnected';
  const health = await checkHealth();
  return health.status === 'ok' ? 'connected' : 'disconnected';
}

/**
 * Fetch (or generate) an evacuation plan for the given user location.
 *
 * In Demo Mode this returns deterministic synthetic data immediately.
 * With a real backend, it would POST the location to /plan and return
 * the server response.
 *
 * @param location   The user's resolved location.
 * @param demoMode   When true, always return mock data regardless of backend.
 * @param blockage   When true in demo mode, activate the simulated blockage.
 */
export async function getEvacuationPlan(
  location: UserLocation,
  demoMode: boolean,
  blockage = false,
): Promise<EvacuationPlan> {
  // ── Demo Mode — always uses mock data ────────────────────────────────────
  if (demoMode || !BACKEND_URL) {
    // Simulate a short network delay so the loading state is visible.
    await _simulatedDelay(600);
    demoAnchor = location;
    return anchoredDemo(blockage);
  }

  // ── Real backend ──────────────────────────────────────────────────────────
  const res = await fetchWithTimeout(`${BACKEND_URL}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      lat: location.lat,
      lon: location.lon,
      node_id: location.node_id,
    }),
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return res.json() as Promise<EvacuationPlan>;
}

/**
 * Simulate a road blockage on an existing plan.
 * In demo mode, returns the pre-built blocked plan.
 * With a real backend, would POST to /plan/replan.
 */
export async function simulateBlockage(
  _currentPlan: EvacuationPlan,
  demoMode: boolean,
): Promise<EvacuationPlan> {
  if (demoMode || !BACKEND_URL) {
    await _simulatedDelay(400);
    return anchoredDemo(true);
  }
  const res = await fetchWithTimeout(`${BACKEND_URL}/plan/replan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scenario_id: _currentPlan.scenario_id,
      block_edges: [['A', 'B'], ['B', 'A']],
    }),
  });
  if (!res.ok) throw new Error(`Replan failed: HTTP ${res.status}`);
  return res.json() as Promise<EvacuationPlan>;
}

/**
 * Clear a simulated blockage and return to the normal plan.
 */
export async function clearBlockage(
  demoMode: boolean,
): Promise<EvacuationPlan> {
  if (demoMode || !BACKEND_URL) {
    await _simulatedDelay(300);
    return anchoredDemo(false);
  }
  const res = await fetchWithTimeout(`${BACKEND_URL}/plan/replan/clear`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Clear blockage failed: HTTP ${res.status}`);
  return res.json() as Promise<EvacuationPlan>;
}

// ── Internal ───────────────────────────────────────────────────────────────

function _simulatedDelay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
