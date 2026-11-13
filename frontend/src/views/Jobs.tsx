import { useState, type ChangeEvent } from 'react';
import { Plus, RefreshCw, Trash2 } from 'lucide-react';
import type { AppActions, AppData } from '../appTypes';
import { JsonBlock } from '../components/JsonBlock';
import { EmptyState, Panel } from '../components/Panel';
import { StatusBadge } from '../components/StatusBadge';
import { shortId, titleCase } from '../lib/format';

export function Jobs({ data, actions }: { data: AppData; actions: AppActions }) {
  const [jobId, setJobId] = useState('');
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!jobId.trim()) return;
    setBusy(true);
    try {
      await actions.trackJob(jobId.trim());
      setJobId('');
    } catch {
      // App-level action already surfaces the error.
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="view-stack">
      <div className="view-heading"><div><span className="eyebrow">Asynchronous execution</span><h1>Jobs</h1><p>Track PostgreSQL-backed reconciliation jobs by ID.</p></div><button className="btn btn-secondary" onClick={() => void actions.refreshJobs()}><RefreshCw size={16}/>Refresh tracked jobs</button></div>
      <Panel title="Track a job" subtitle="The backend has a get-by-ID endpoint, not a list-jobs endpoint, so this console stores only the IDs you submit or add locally.">
        <div className="inline-form"><input value={jobId} onChange={(e: ChangeEvent<HTMLInputElement>) => setJobId(e.target.value)} placeholder="Job ID"/><button className="btn btn-primary" disabled={!jobId.trim() || busy} onClick={() => void add()}><Plus size={16}/>Track</button></div>
      </Panel>

      {!data.trackedJobs.length ? <Panel><EmptyState title="No tracked jobs">Queue an async reconciliation or enter a known job ID.</EmptyState></Panel> : (
        <div className="job-grid">{data.trackedJobs.map((job) => <Panel key={job.id} title={`${titleCase(job.job_type)} · ${shortId(job.id, 12)}`} action={<button className="icon-button" onClick={() => actions.removeJob(job.id)} aria-label="Remove tracked job"><Trash2 size={16}/></button>}><div className="detail-list"><div><span>Status</span><StatusBadge status={job.status}/></div><div><span>Attempts</span><strong>{job.attempts}</strong></div><div><span>Last error</span><strong>{job.last_error || '—'}</strong></div></div>{job.result && <details className="job-result"><summary>Result</summary><JsonBlock value={job.result} compact /></details>}</Panel>)}</div>
      )}
    </div>
  );
}
