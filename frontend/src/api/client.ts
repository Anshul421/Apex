import type {
  AgentEvent,
  AsyncJobAccepted,
  Athlete,
  JobRecord,
  Plan,
  ReconcileResult,
} from './types';

const runtimeBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
const API_BASE = (runtimeBase || '/api/v1').replace(/\/$/, '');

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  const bearer = import.meta.env.VITE_BEARER_TOKEN as string | undefined;
  const devUser = import.meta.env.VITE_DEV_USER as string | undefined;
  const devTenant = import.meta.env.VITE_DEV_TENANT as string | undefined;

  // Bearer authentication takes precedence; dev identity headers are a local fallback.
  if (bearer) {
    headers.Authorization = `Bearer ${bearer}`;
  } else {
    if (devUser) headers['X-Dev-User'] = devUser;
    if (devTenant) headers['X-Dev-Tenant'] = devTenant;
  }
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...authHeaders(),
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init.headers || {}),
    },
  });

  if (!response.ok) {
    let details: unknown = undefined;
    let message = `${response.status} ${response.statusText}`;
    try {
      details = await response.json();
      if (
        details &&
        typeof details === 'object' &&
        'detail' in details &&
        typeof (details as { detail?: unknown }).detail === 'string'
      ) {
        message = (details as { detail: string }).detail;
      }
    } catch {
      // Preserve the HTTP status text when the body is not JSON.
    }
    const error = new Error(message) as Error & { status?: number; details?: unknown };
    error.status = response.status;
    error.details = details;
    throw error;
  }

  // Successful no-content responses have no JSON body to parse.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function bodyWithOptionalReason(reason?: string): string {
  return JSON.stringify(reason?.trim() ? { reason: reason.trim() } : {});
}

export const api = {
  baseUrl: API_BASE,

  async healthLive(): Promise<{ status: string }> {
    return request('/health/live');
  },

  async healthReady(): Promise<{ status: string }> {
    return request('/health/ready');
  },

  async bootstrap(): Promise<{ athlete: Athlete }> {
    return request('/simulator/bootstrap', { method: 'POST' });
  },

  async createAthlete(payload: { name: string; objective: string; timezone_name?: string }): Promise<Athlete> {
    return request('/athletes', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getAthlete(athleteId: string): Promise<Athlete> {
    return request(`/athletes/${encodeURIComponent(athleteId)}`);
  },

  async listPlans(athleteId: string): Promise<Plan[]> {
    return request(`/athletes/${encodeURIComponent(athleteId)}/plans`);
  },

  async currentPlan(athleteId: string): Promise<Plan> {
    return request(`/athletes/${encodeURIComponent(athleteId)}/plans/current`);
  },

  async events(athleteId: string, runId?: string): Promise<AgentEvent[]> {
    const query = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
    return request(`/athletes/${encodeURIComponent(athleteId)}/events${query}`);
  },

  async reconcile(athleteId: string, reason?: string): Promise<ReconcileResult> {
    return request(`/athletes/${encodeURIComponent(athleteId)}/autopilot/reconcile`, {
      method: 'POST',
      body: bodyWithOptionalReason(reason),
    });
  },

  async reconcileAsync(athleteId: string, reason?: string): Promise<AsyncJobAccepted> {
    return request(`/athletes/${encodeURIComponent(athleteId)}/autopilot/reconcile-async`, {
      method: 'POST',
      body: bodyWithOptionalReason(reason),
    });
  },

  async getJob(jobId: string): Promise<JobRecord> {
    return request(`/jobs/${encodeURIComponent(jobId)}`);
  },

  async injectWellnessDrop(athleteId: string): Promise<Record<string, unknown>> {
    return request(`/simulator/athletes/${encodeURIComponent(athleteId)}/inject/wellness-drop`, { method: 'POST' });
  },

  async injectMatchMove(athleteId: string, hours?: number): Promise<Record<string, unknown>> {
    const query = Number.isFinite(hours) ? `?hours=${encodeURIComponent(String(hours))}` : '';
    return request(`/simulator/athletes/${encodeURIComponent(athleteId)}/inject/match-move${query}`, { method: 'POST' });
  },

  async injectBookingConflict(athleteId: string): Promise<Record<string, unknown>> {
    return request(`/simulator/athletes/${encodeURIComponent(athleteId)}/inject/booking-conflict`, { method: 'POST' });
  },

  async injectStaleGps(athleteId: string): Promise<Record<string, unknown>> {
    return request(`/simulator/athletes/${encodeURIComponent(athleteId)}/inject/stale-gps`, { method: 'POST' });
  },

  async injectInfeasible(athleteId: string): Promise<Record<string, unknown>> {
    return request(`/simulator/athletes/${encodeURIComponent(athleteId)}/inject/infeasible`, { method: 'POST' });
  },
};
