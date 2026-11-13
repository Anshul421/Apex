import { useMemo, useState, type ChangeEvent } from 'react';
import { Search } from 'lucide-react';
import type { AppData } from '../appTypes';
import { JsonBlock } from '../components/JsonBlock';
import { EmptyState, Panel } from '../components/Panel';
import { formatDateTime, shortId, titleCase } from '../lib/format';

export function ActivityView({ data }: { data: AppData }) {
  const [runId, setRunId] = useState('');
  const [query, setQuery] = useState('');
  const [selectedEventId, setSelectedEventId] = useState('');
  const runIds = useMemo(() => [...new Set(data.events.map((event) => event.run_id))].reverse(), [data.events]);
  const filtered = useMemo(() => data.events.filter((event) => {
    const runMatch = !runId || event.run_id === runId;
    const q = query.trim().toLowerCase();
    const queryMatch = !q || event.event_type.toLowerCase().includes(q) || JSON.stringify(event.payload).toLowerCase().includes(q);
    return runMatch && queryMatch;
  }), [data.events, query, runId]);
  const selected = data.events.find((event) => event.id === selectedEventId) || filtered.at(-1) || null;

  return (
    <div className="view-stack">
      <div className="view-heading"><div><span className="eyebrow">Agent observability</span><h1>Activity</h1><p>Audit the action-observation-replan loop through persisted agent events.</p></div></div>
      <Panel>
        <div className="filter-bar">
          <label className="search-box"><Search size={16}/><input value={query} onChange={(e: ChangeEvent<HTMLInputElement>) => setQuery(e.target.value)} placeholder="Search event type or payload" /></label>
          <select value={runId} onChange={(e: ChangeEvent<HTMLSelectElement>) => setRunId(e.target.value)}><option value="">All runs</option>{runIds.map((id) => <option key={id} value={id}>Run {shortId(id, 16)}</option>)}</select>
        </div>
      </Panel>

      {!data.events.length ? <Panel><EmptyState title="No agent events">Run reconciliation to create the audit trail.</EmptyState></Panel> : (
        <div className="activity-layout">
          <Panel title="Event stream" subtitle={`${filtered.length} matching events`}>
            <div className="event-list">{filtered.map((event) => <button key={event.id} className={`event-row ${selected?.id === event.id ? 'active' : ''}`} onClick={() => setSelectedEventId(event.id)}><div className="event-marker"/><div><strong>{titleCase(event.event_type)}</strong><span>{formatDateTime(event.created_at)}</span><small>run {shortId(event.run_id, 12)} {event.plan_id ? `· plan ${shortId(event.plan_id, 10)}` : ''}</small></div></button>)}</div>
          </Panel>
          <Panel title={selected ? titleCase(selected.event_type) : 'Event detail'} subtitle={selected ? `${formatDateTime(selected.created_at)} · run ${selected.run_id}` : undefined}>
            {selected ? <JsonBlock value={selected.payload} /> : <EmptyState title="Select an event">Choose an event to inspect its payload.</EmptyState>}
          </Panel>
        </div>
      )}
    </div>
  );
}
