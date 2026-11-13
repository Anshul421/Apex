import { useMemo, useState } from 'react';
import { ArrowDown, GitCompareArrows } from 'lucide-react';
import type { Plan } from '../api/types';
import type { AppData } from '../appTypes';
import { JsonBlock } from '../components/JsonBlock';
import { EmptyState, Panel } from '../components/Panel';
import { StatusBadge } from '../components/StatusBadge';
import { formatDateTime, shortId, titleCase } from '../lib/format';

function DiffBucket({ label, values }: { label: string; values?: string[] }) {
  return (
    <div className="diff-bucket">
      <span>{label}</span>
      <strong>{values?.length ?? 0}</strong>
      <div className="tag-row">{values?.map((value) => <span className="mini-tag" key={value}>{value}</span>)}</div>
    </div>
  );
}

export function Plans({ data }: { data: AppData }) {
  const [selectedId, setSelectedId] = useState('');
  const selected = useMemo<Plan | null>(() => {
    if (!data.plans.length) return null;
    return data.plans.find((plan) => plan.id === selectedId) || data.plans.at(-1) || null;
  }, [data.plans, selectedId]);

  if (!data.plans.length) {
    return <div className="view-stack"><div className="view-heading"><div><span className="eyebrow">Plan lineage</span><h1>Plans</h1><p>Inspect versioned schedules, diffs, constraints, and verification history.</p></div></div><Panel><EmptyState title="No plan versions">Run reconciliation to create the first immutable plan version.</EmptyState></Panel></div>;
  }

  return (
    <div className="view-stack">
      <div className="view-heading"><div><span className="eyebrow">Plan lineage</span><h1>Plans</h1><p>Every returned plan version remains separately inspectable.</p></div></div>

      <div className="version-strip">
        {data.plans.map((plan, index) => (
          <button key={plan.id} className={`version-node ${selected?.id === plan.id ? 'active' : ''}`} onClick={() => setSelectedId(plan.id)}>
            <span>V{plan.version}</span><StatusBadge status={plan.status} /><small>{formatDateTime(plan.created_at)}</small>
            {index < data.plans.length - 1 && <ArrowDown size={14} className="version-arrow" />}
          </button>
        ))}
      </div>

      {selected && (
        <>
          <div className="dashboard-grid two-one">
            <Panel title={`Plan V${selected.version}`} subtitle={`Plan ID ${selected.id}`}>
              <div className="detail-list">
                <div><span>Status</span><StatusBadge status={selected.status} /></div>
                <div><span>Reason</span><strong>{titleCase(selected.reason)}</strong></div>
                <div><span>Parent plan</span><code title={selected.parent_plan_id || ''}>{shortId(selected.parent_plan_id, 16)}</code></div>
                <div><span>World hash</span><code title={selected.world_state_hash}>{shortId(selected.world_state_hash, 16)}</code></div>
                <div><span>Created</span><strong>{formatDateTime(selected.created_at)}</strong></div>
              </div>
            </Panel>
            <Panel title="Revision diff" subtitle="Machine-readable minimum-disruption changes.">
              <div className="diff-grid">
                <DiffBucket label="Added" values={selected.diff.added} />
                <DiffBucket label="Changed" values={selected.diff.changed} />
                <DiffBucket label="Removed" values={selected.diff.removed} />
                <DiffBucket label="Unchanged" values={selected.diff.unchanged} />
              </div>
            </Panel>
          </div>

          <Panel title="Session schedule" subtitle="The selected plan version, not the current plan only.">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Logical key</th><th>Type</th><th>Start</th><th>Duration</th><th>Load</th><th>Intensity</th><th>Facility</th><th>Status</th></tr></thead>
                <tbody>{selected.sessions.map((session) => (
                  <tr key={session.id}><td><code>{session.logical_key}</code></td><td>{titleCase(session.session_type)}</td><td>{formatDateTime(session.start_time)}</td><td>{session.duration_minutes} min</td><td>{session.intended_load}</td><td><StatusBadge status={session.intensity} /></td><td>{session.facility || '—'}</td><td><StatusBadge status={session.status} /></td></tr>
                ))}</tbody>
              </table>
            </div>
          </Panel>

          <div className="dashboard-grid equal">
            <Panel title="Intent" subtitle="Structured semantic intent persisted with the plan."><JsonBlock value={selected.intent} /></Panel>
            <Panel title="Diff details" subtitle="Before/after details returned by the backend."><JsonBlock value={selected.diff.details || {}} /></Panel>
          </div>

          <Panel title="Lineage summary" subtitle="Parent-child relationships are backend records, not inferred from timestamps.">
            <div className="lineage-row"><GitCompareArrows size={18} /><code>{selected.parent_plan_id || 'ROOT'}</code><span>→</span><code>{selected.id}</code></div>
          </Panel>
        </>
      )}
    </div>
  );
}
