import { titleCase } from '../lib/format';

function toneFor(status: string): string {
  const normalized = status.toLowerCase();
  if (['ok', 'ready', 'verified', 'executed', 'succeeded', 'confirmed', 'optimal', 'feasible', 'fresh'].some((item) => normalized.includes(item))) return 'success';
  if (['failed', 'error', 'invalidated', 'infeasible', 'stale', 'blocked'].some((item) => normalized.includes(item))) return 'danger';
  if (['pending', 'running', 'executing', 'proposed', 'checking'].some((item) => normalized.includes(item))) return 'warning';
  return 'neutral';
}

export function StatusBadge({ status }: { status?: string | null }) {
  const value = status || 'unknown';
  return <span className={`status-badge status-${toneFor(value)}`}>{titleCase(value)}</span>;
}
