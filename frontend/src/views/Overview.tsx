import { Activity, CheckCircle2, Clock3, Database, GitBranch, ShieldCheck } from 'lucide-react';
import type { AppData } from '../appTypes';
import { EmptyState, Metric, Panel } from '../components/Panel';
import { StatusBadge } from '../components/StatusBadge';
import { formatDateTime, humanValue, shortId, titleCase } from '../lib/format';

function latestEventByType(events: AppData['events'], types: string[]) {
  return [...events].reverse().find((event) => types.includes(event.event_type));
}

export function Overview({ data }: { data: AppData }) {
  const current = data.plans.at(-1) || null;
  const latestVerification = current?.verification_runs.at(-1) || null;
  const latestWorld = latestEventByType(data.events, ['WORLD_REOBSERVED_AFTER_ACTIONS', 'WORLD_OBSERVED']);
  const latestIntent = latestEventByType(data.events, ['INTENT_CREATED']);
  const latestOptimizer = latestEventByType(data.events, ['OPTIMIZER_RESULT']);
  const failedConstraints = current?.constraints.filter((item) => !item.passed) || [];
  const latestEvent = data.events.at(-1) || null;

  return (
    <div className="view-stack">
      <div className="view-heading">
        <div>
          <span className="eyebrow">Operations overview</span>
          <h1>{data.athlete?.name}</h1>
          <p>{data.athlete?.objective}</p>
        </div>
        <div className="heading-statuses">
          <StatusBadge status={data.health.live} />
          <StatusBadge status={data.health.ready} />
        </div>
      </div>

      <div className="metrics-grid">
        <Metric label="Current plan" value={current ? `V${current.version}` : '—'} hint={current ? <StatusBadge status={current.status} /> : 'No plan yet'} />
        <Metric label="Sessions" value={current?.sessions.length ?? '—'} hint="From current plan" />
        <Metric label="Verification" value={latestVerification ? (latestVerification.passed ? 'Passed' : 'Failed') : '—'} hint={latestVerification ? formatDateTime(latestVerification.created_at) : 'No verification run'} />
        <Metric label="Constraint failures" value={current ? failedConstraints.length : '—'} hint={current ? `${current.constraints.length} checks returned` : 'No constraint data'} />
      </div>

      <div className="dashboard-grid two-one">
        <Panel title="Plan control" subtitle="Latest immutable plan version and lineage.">
          {current ? (
            <div className="detail-list">
              <div><span><GitBranch size={15} /> Version</span><strong>V{current.version}</strong></div>
              <div><span><ShieldCheck size={15} /> Status</span><StatusBadge status={current.status} /></div>
              <div><span><Clock3 size={15} /> Created</span><strong>{formatDateTime(current.created_at)}</strong></div>
              <div><span><Database size={15} /> World hash</span><code title={current.world_state_hash}>{shortId(current.world_state_hash, 14)}</code></div>
              <div><span><Activity size={15} /> Trigger</span><strong>{titleCase(current.reason)}</strong></div>
              <div><span><GitBranch size={15} /> Parent</span><code title={current.parent_plan_id || ''}>{shortId(current.parent_plan_id, 14)}</code></div>
            </div>
          ) : (
            <EmptyState title="No plan has been created">Run reconciliation after the athlete world is available.</EmptyState>
          )}
        </Panel>

        <Panel title="System evidence" subtitle="Derived from the backend event stream, not frontend constants.">
          <div className="evidence-stack">
            <div className="evidence-card">
              <div className="evidence-title">World state</div>
              {latestWorld ? (
                <>
                  <div className="tag-row">
                    {latestWorld.payload.freshness && typeof latestWorld.payload.freshness === 'object' &&
                      Object.entries(latestWorld.payload.freshness as Record<string, unknown>).map(([key, value]) => (
                        <span className="mini-tag" key={key}>{titleCase(key)}: {humanValue(value)}</span>
                      ))}
                  </div>
                  <small>{formatDateTime(latestWorld.created_at)}</small>
                </>
              ) : <span className="muted">No world observation event yet.</span>}
            </div>
            <div className="evidence-card">
              <div className="evidence-title">Intent provider</div>
              {latestIntent && latestIntent.payload._meta && typeof latestIntent.payload._meta === 'object' ? (
                <div className="tag-row">
                  {Object.entries(latestIntent.payload._meta as Record<string, unknown>)
                    .filter(([, value]) => value !== null && value !== undefined && value !== '')
                    .map(([key, value]) => <span className="mini-tag" key={key}>{titleCase(key)}: {humanValue(value)}</span>)}
                </div>
              ) : <span className="muted">No intent event yet.</span>}
            </div>
            <div className="evidence-card">
              <div className="evidence-title">Optimizer</div>
              {latestOptimizer ? (
                <div className="tag-row">
                  <span className="mini-tag">Status: {humanValue(latestOptimizer.payload.status)}</span>
                  <span className="mini-tag">Backend: {humanValue(latestOptimizer.payload.backend)}</span>
                  <span className="mini-tag">Objective: {humanValue(latestOptimizer.payload.objective_value)}</span>
                </div>
              ) : <span className="muted">No optimizer event yet.</span>}
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Upcoming plan sessions" subtitle="Schedule returned by the current plan.">
        {current?.sessions.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Session</th><th>Start</th><th>Duration</th><th>Load</th><th>Intensity</th><th>Facility</th><th>Status</th></tr></thead>
              <tbody>
                {current.sessions.map((session) => (
                  <tr key={session.id}>
                    <td><strong>{titleCase(session.session_type)}</strong><small>{session.logical_key}</small></td>
                    <td>{formatDateTime(session.start_time)}</td>
                    <td>{session.duration_minutes} min</td>
                    <td>{session.intended_load}</td>
                    <td><StatusBadge status={session.intensity} /></td>
                    <td>{session.facility || '—'}</td>
                    <td><StatusBadge status={session.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState title="No sessions">No current schedule exists.</EmptyState>}
      </Panel>

      <Panel title="Latest activity" subtitle="Most recent event emitted by the autonomous loop.">
        {latestEvent ? (
          <div className="latest-activity">
            <CheckCircle2 size={20} />
            <div><strong>{titleCase(latestEvent.event_type)}</strong><span>{formatDateTime(latestEvent.created_at)} · run {shortId(latestEvent.run_id, 12)}</span></div>
          </div>
        ) : <EmptyState title="No activity yet">Reconcile to generate an auditable event trail.</EmptyState>}
      </Panel>
    </div>
  );
}
