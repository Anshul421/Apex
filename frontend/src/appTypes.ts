import type { AgentEvent, Athlete, HealthStatus, JobRecord, Plan, ReconcileResult } from './api/types';

export interface AppData {
  athlete: Athlete | null;
  plans: Plan[];
  events: AgentEvent[];
  health: HealthStatus;
  loading: boolean;
  error: string | null;
  lastReconcile: ReconcileResult | null;
  trackedJobs: JobRecord[];
}

export interface AppActions {
  setActiveAthlete: (athleteId: string) => Promise<void>;
  bootstrapAthlete: () => Promise<void>;
  createAthlete: (payload: { name: string; objective: string; timezone_name?: string }) => Promise<void>;
  refresh: () => Promise<void>;
  reconcile: (reason?: string) => Promise<ReconcileResult>;
  reconcileAsync: (reason?: string) => Promise<string>;
  refreshJobs: () => Promise<void>;
  trackJob: (jobId: string) => Promise<void>;
  removeJob: (jobId: string) => void;
  clearError: () => void;
}
