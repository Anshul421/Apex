import { useMemo, useState, type ChangeEvent } from 'react';
import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react';
import type { AppData } from '../appTypes';
import { JsonBlock } from '../components/JsonBlock';
import { EmptyState, Metric, Panel } from '../components/Panel';
import { StatusBadge } from '../components/StatusBadge';
import { formatDateTime, humanValue, titleCase } from '../lib/format';

export function Verification({ data }: { data: AppData }) {
  const [planId, setPlanId] = useState('');
  const plan = useMemo(() => data.plans.find((item) => item.id === planId) || data.plans.at(-1) || null, [data.plans, planId]);
  const latest = plan?.verification_runs.at(-1) || null;
  const passed = plan?.constraints.filter((item) => item.passed).length ?? 0;
  const failed = plan?.constraints.filter((item) => !item.passed).length ?? 0;

  return (
    <div className="view-stack">
      <div className="view-heading"><div><span className="eyebrow">Independent verification</span><h1>Safety & correctness</h1><p>Constraint and end-state checks are rendered separately from planner intent.</p></div>{data.plans.length > 0 && <select value={plan?.id || ''} onChange={(e: ChangeEvent<HTMLSelectElement>) => setPlanId(e.target.value)}>{[...data.plans].reverse().map((item) => <option key={item.id} value={item.id}>Plan V{item.version} · {titleCase(item.status)}</option>)}</select>}</div>

      {!plan ? <Panel><EmptyState title="No verification data">A plan must exist before verification evidence can be shown.</EmptyState></Panel> : (
        <>
          <div className="metrics-grid">
            <Metric label="Latest verdict" value={latest ? (latest.passed ? 'Passed' : 'Failed') : '—'} hint={latest ? <StatusBadge status={latest.passed ? 'verified' : 'failed'} /> : 'No verification run'} />
            <Metric label="Passed checks" value={passed} hint={`${plan.constraints.length} total checks`} />
            <Metric label="Failed checks" value={failed} hint={failed ? 'Requires attention' : 'None returned'} />
            <Metric label="Verification runs" value={plan.verification_runs.length} hint={`Plan V${plan.version}`} />
          </div>

          <Panel title="Constraint results" subtitle="Limits and measured values come directly from the backend evaluator.">
            {plan.constraints.length ? <div className="table-wrap"><table><thead><tr><th>Constraint</th><th>Limit</th><th>Measured</th><th>Result</th><th>Details</th></tr></thead><tbody>{plan.constraints.map((constraint, index) => <tr key={`${constraint.constraint_type}-${index}`}><td><strong>{titleCase(constraint.constraint_type)}</strong></td><td>{humanValue(constraint.limit)}</td><td>{humanValue(constraint.measured_value)}</td><td>{constraint.passed ? <span className="result-pass"><CheckCircle2 size={16}/> Pass</span> : <span className="result-fail"><ShieldAlert size={16}/> Fail</span>}</td><td><details><summary>Inspect</summary><JsonBlock value={constraint.details} compact /></details></td></tr>)}</tbody></table></div> : <EmptyState title="No constraint rows">This plan has no persisted constraint results.</EmptyState>}
          </Panel>

          <div className="dashboard-grid equal">
            <Panel title="Verification history" subtitle="Each run is persisted independently.">
              <div className="timeline-list">{[...plan.verification_runs].reverse().map((run) => <div className="timeline-item" key={run.id}><div className={`timeline-dot ${run.passed ? 'pass' : 'fail'}`} /> <div><strong>{run.passed ? 'Verification passed' : 'Verification failed'}</strong><span>{formatDateTime(run.created_at)}</span>{run.violations.length > 0 && <div className="violation-list">{run.violations.map((violation) => <span key={violation}><AlertTriangle size={13}/>{violation}</span>)}</div>}</div></div>)}</div>
            </Panel>
            <Panel title="Latest state snapshot" subtitle="Evidence captured by the verifier at evaluation time.">
              {latest ? <JsonBlock value={latest.state_snapshot} /> : <EmptyState title="No snapshot">No verification run exists for this plan.</EmptyState>}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
