import { useState, type ChangeEvent, type FormEvent } from 'react';
import { ArrowRight, FlaskConical, Plus } from 'lucide-react';
import type { AppActions } from '../appTypes';
import { Panel } from './Panel';

export function AthleteGate({ actions }: { actions: AppActions }) {
  const [athleteId, setAthleteId] = useState('');
  const [name, setName] = useState('');
  const [objective, setObjective] = useState('');
  const [timezone, setTimezone] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch {
      // App-level actions already surface their API error in the global banner.
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="gate-grid">
      <Panel title="Connect an athlete" subtitle="The backend does not expose an athlete-list endpoint, so select a known athlete by ID.">
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            if (!athleteId.trim()) return;
            void run('connect', () => actions.setActiveAthlete(athleteId.trim()));
          }}
        >
          <label>
            Athlete ID
            <input value={athleteId} onChange={(event: ChangeEvent<HTMLInputElement>) => setAthleteId(event.target.value)} placeholder="Enter backend athlete ID" />
          </label>
          <button className="btn btn-primary" disabled={!athleteId.trim() || busy !== null}>
            Connect <ArrowRight size={16} />
          </button>
        </form>
      </Panel>

      <Panel title="Bootstrap simulator" subtitle="Create the synthetic AthleteOps scenario exposed by the backend.">
        <div className="callout muted-callout">
          No example athlete data is embedded in this frontend. This action asks the backend to create the scenario and returns the athlete ID.
        </div>
        <button className="btn btn-secondary" disabled={busy !== null} onClick={() => void run('bootstrap', actions.bootstrapAthlete)}>
          <FlaskConical size={16} /> {busy === 'bootstrap' ? 'Bootstrapping…' : 'Bootstrap scenario'}
        </button>
      </Panel>

      <Panel title="Create athlete" subtitle="Create a real athlete record using the API contract.">
        <form
          className="stack-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            if (!name.trim() || !objective.trim()) return;
            void run('create', () => actions.createAthlete({
              name: name.trim(),
              objective: objective.trim(),
              ...(timezone.trim() ? { timezone_name: timezone.trim() } : {}),
            }));
          }}
        >
          <label>
            Name
            <input value={name} onChange={(event: ChangeEvent<HTMLInputElement>) => setName(event.target.value)} required />
          </label>
          <label>
            Objective
            <textarea value={objective} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setObjective(event.target.value)} rows={3} required />
          </label>
          <label>
            Timezone <span className="field-note">optional; backend default applies when blank</span>
            <input value={timezone} onChange={(event: ChangeEvent<HTMLInputElement>) => setTimezone(event.target.value)} placeholder="IANA timezone" />
          </label>
          <button className="btn btn-primary" disabled={!name.trim() || !objective.trim() || busy !== null}>
            <Plus size={16} /> {busy === 'create' ? 'Creating…' : 'Create athlete'}
          </button>
        </form>
      </Panel>
    </div>
  );
}
