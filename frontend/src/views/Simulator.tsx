import { useState, type ChangeEvent } from 'react';
import { AlertTriangle, CalendarClock, CloudOff, HeartPulse, Play, RefreshCw, RouteOff, TimerReset } from 'lucide-react';
import type { ReconcileResult } from '../api/types';
import type { AppActions, AppData } from '../appTypes';
import { JsonBlock } from '../components/JsonBlock';
import { EmptyState, Panel } from '../components/Panel';
import { StatusBadge } from '../components/StatusBadge';
import { api } from '../api/client';

interface ScenarioAction {
  key: string;
  title: string;
  description: string;
  icon: typeof HeartPulse;
  run: (athleteId: string, matchHours?: number) => Promise<Record<string, unknown>>;
  prerequisite?: string;
}

const scenarioActions: ScenarioAction[] = [
  { key: 'wellness', title: 'Wellness change', description: 'Inject a new wellness observation and force the next reconciliation to reason over a changed world.', icon: HeartPulse, run: (id) => api.injectWellnessDrop(id) },
  { key: 'match', title: 'Move fixture', description: 'Revise the match timing. Leave hours blank to use the backend-configured route default.', icon: CalendarClock, run: (id, hours) => api.injectMatchMove(id, hours) },
  { key: 'booking', title: 'Booking conflict', description: 'Invalidate a facility slot used by the latest plan so action execution must recover.', icon: RouteOff, run: (id) => api.injectBookingConflict(id), prerequisite: 'Requires an existing plan with a booked facility session.' },
  { key: 'stale', title: 'Stale GPS', description: 'Inject stale source data to exercise the policy boundary that blocks certification.', icon: CloudOff, run: (id) => api.injectStaleGps(id) },
  { key: 'infeasible', title: 'Infeasible availability', description: 'Replace athlete availability with a world that cannot produce a legal schedule.', icon: AlertTriangle, run: (id) => api.injectInfeasible(id) },
];

export function Simulator({ data, actions }: { data: AppData; actions: AppActions }) {
  const [reason, setReason] = useState('');
  const [matchHours, setMatchHours] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [scenarioResult, setScenarioResult] = useState<Record<string, unknown> | null>(null);
  const [runResult, setRunResult] = useState<ReconcileResult | null>(data.lastReconcile);
  const [localError, setLocalError] = useState<string | null>(null);

  if (!data.athlete) return <Panel><EmptyState title="No active athlete">Connect an athlete first.</EmptyState></Panel>;

  const executeScenario = async (scenario: ScenarioAction) => {
    setBusy(scenario.key);
    setLocalError(null);
    try {
      const parsedHours = matchHours.trim() === '' ? undefined : Number(matchHours);
      const result = await scenario.run(data.athlete!.id, Number.isFinite(parsedHours) ? parsedHours : undefined);
      setScenarioResult({ scenario: scenario.key, ...result });
      await actions.refresh();
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : 'Simulator request failed');
    } finally {
      setBusy(null);
    }
  };

  const executeReconcile = async (asyncMode: boolean) => {
    setBusy(asyncMode ? 'async' : 'sync');
    setLocalError(null);
    try {
      if (asyncMode) {
        const jobId = await actions.reconcileAsync(reason || undefined);
        setScenarioResult({ job_id: jobId, status: 'submitted' });
      } else {
        const result = await actions.reconcile(reason || undefined);
        setRunResult(result);
      }
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : 'Reconciliation failed');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="view-stack">
      <div className="view-heading"><div><span className="eyebrow">Controlled environment</span><h1>Simulator & reconcile</h1><p>Trigger backend-supported world changes, then observe whether the agent repairs or refuses safely.</p></div></div>

      {localError && <div className="callout error-callout">{localError}</div>}

      <div className="dashboard-grid equal">
        <Panel title="Run autonomous reconciliation" subtitle="Reason is optional. When blank, the backend request model supplies its own default.">
          <div className="stack-form">
            <label>Reason <span className="field-note">optional</span><input value={reason} onChange={(e: ChangeEvent<HTMLInputElement>) => setReason(e.target.value)} placeholder="Custom trigger reason" /></label>
            <div className="button-row">
              <button className="btn btn-primary" disabled={busy !== null} onClick={() => void executeReconcile(false)}><Play size={16}/>{busy === 'sync' ? 'Running…' : 'Reconcile now'}</button>
              <button className="btn btn-secondary" disabled={busy !== null} onClick={() => void executeReconcile(true)}><TimerReset size={16}/>{busy === 'async' ? 'Submitting…' : 'Queue async run'}</button>
            </div>
          </div>
          {runResult && <div className="result-card"><div><strong>Last reconcile result</strong><StatusBadge status={runResult.status}/></div><JsonBlock value={runResult} compact /></div>}
        </Panel>

        <Panel title="Latest simulator response" subtitle="Raw response from the most recent injection or queued job.">
          {scenarioResult ? <JsonBlock value={scenarioResult} /> : <EmptyState title="No simulator action yet">Choose a scenario below.</EmptyState>}
        </Panel>
      </div>

      <Panel title="Failure and change scenarios" subtitle="These are the exact simulator routes present in the backend.">
        <div className="scenario-grid">
          {scenarioActions.map((scenario) => {
            const Icon = scenario.icon;
            return <div className="scenario-card" key={scenario.key}><div className="scenario-icon"><Icon size={19}/></div><div><h3>{scenario.title}</h3><p>{scenario.description}</p>{scenario.prerequisite && <small>{scenario.prerequisite}</small>}{scenario.key === 'match' && <label className="compact-field">Hours <input type="number" value={matchHours} onChange={(e: ChangeEvent<HTMLInputElement>) => setMatchHours(e.target.value)} placeholder="backend default" /></label>}<button className="btn btn-ghost" disabled={busy !== null} onClick={() => void executeScenario(scenario)}><RefreshCw size={15}/>{busy === scenario.key ? 'Applying…' : 'Inject change'}</button></div></div>;
          })}
        </div>
      </Panel>
    </div>
  );
}
