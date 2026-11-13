export interface Athlete {
  id: string;
  tenant_id: string;
  name: string;
  objective: string;
  timezone_name: string;
  created_at: string;
}

export interface SessionRecord {
  id: string;
  logical_key: string;
  session_type: string;
  start_time: string;
  duration_minutes: number;
  intended_load: number;
  intensity: string;
  facility: string | null;
  status: string;
}

export interface ConstraintResult {
  constraint_type: string;
  limit: number | null;
  measured_value: number | null;
  passed: boolean;
  details: Record<string, unknown>;
}

export interface VerificationRun {
  id: string;
  passed: boolean;
  violations: string[];
  state_snapshot: Record<string, unknown>;
  created_at: string;
}

export interface PlanDiff {
  added?: string[];
  changed?: string[];
  unchanged?: string[];
  removed?: string[];
  details?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface Plan {
  id: string;
  athlete_id: string;
  version: number;
  parent_plan_id: string | null;
  reason: string;
  created_at: string;
  world_state_hash: string;
  status: string;
  intent: Record<string, unknown>;
  diff: PlanDiff;
  sessions: SessionRecord[];
  constraints: ConstraintResult[];
  verification_runs: VerificationRun[];
}

export interface AgentEvent {
  id: string;
  run_id: string;
  plan_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ReconcileResult {
  run_id: string;
  status: string;
  plan_id?: string;
  plan_version?: number;
  parent_plan_id?: string | null;
  verification?: Record<string, unknown>;
  diff?: PlanDiff;
  optimizer_backend?: string | null;
  conflicts?: string[];
  error?: string | null;
  world_state_hash?: string;
  noop?: boolean;
}

export interface JobRecord {
  id: string;
  job_type: string;
  status: string;
  attempts: number;
  last_error: string | null;
  result: Record<string, unknown> | null;
}

export interface HealthStatus {
  live: 'ok' | 'error' | 'checking';
  ready: 'ready' | 'error' | 'checking';
}

export interface AsyncJobAccepted {
  job_id: string;
  status: string;
}

export interface ApiErrorShape {
  status: number;
  message: string;
  details?: unknown;
}
