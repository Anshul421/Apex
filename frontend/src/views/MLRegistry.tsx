import { DatabaseZap, FlaskConical, LockKeyhole, ServerCog } from 'lucide-react';
import { Panel } from '../components/Panel';

export function MLRegistry() {
  return (
    <div className="view-stack">
      <div className="view-heading"><div><span className="eyebrow">ML experiment tracking</span><h1>Model registry</h1><p>The repository contains ML training and PostgreSQL registry tables, but the inspected REST router does not expose them.</p></div></div>
      <div className="capability-card">
        <div className="capability-icon"><LockKeyhole size={28}/></div>
        <div><h2>Frontend intentionally does not fabricate ML metrics</h2><p>Training runs, experiment metrics, candidate aliases, artifact URIs, and model versions exist in backend storage code. Because there is no read API for those records, this page remains a capability boundary instead of embedding build-time JSON as if it were live state.</p></div>
      </div>
      <div className="dashboard-grid equal">
        <Panel title="Backend capability detected">
          <div className="feature-list"><span><FlaskConical size={17}/>Experiment and run lineage tables</span><span><DatabaseZap size={17}/>Model version registry with stage and alias</span><span><ServerCog size={17}/>Artifact URI, input schema, metrics, and selected-model fields</span></div>
        </Panel>
        <Panel title="Required API surface for a live dashboard">
          <div className="feature-list"><span>Read experiments and runs</span><span>Read model versions and aliases</span><span>Read one run with metrics and artifact metadata</span><span>Tenant/auth scope those routes consistently</span></div>
        </Panel>
      </div>
    </div>
  );
}
