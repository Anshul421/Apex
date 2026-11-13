import { Code2, KeyRound, Network, Shield } from 'lucide-react';
import { api } from '../api/client';
import { Panel } from '../components/Panel';

export function Settings() {
  const bearerConfigured = Boolean(import.meta.env.VITE_BEARER_TOKEN);
  const devHeadersConfigured = Boolean(import.meta.env.VITE_DEV_USER || import.meta.env.VITE_DEV_TENANT);
  return (
    <div className="view-stack">
      <div className="view-heading"><div><span className="eyebrow">Runtime configuration</span><h1>Frontend settings</h1><p>Read-only build/runtime configuration. Secrets are not editable from the browser UI.</p></div></div>
      <div className="dashboard-grid equal">
        <Panel title="API connection"><div className="detail-list"><div><span><Network size={15}/> Base URL</span><code>{api.baseUrl}</code></div><div><span><KeyRound size={15}/> Bearer token</span><strong>{bearerConfigured ? 'Configured at build/runtime' : 'Not configured'}</strong></div><div><span><Code2 size={15}/> Dev headers</span><strong>{devHeadersConfigured ? 'Configured at build/runtime' : 'Not configured; backend defaults may apply'}</strong></div></div></Panel>
        <Panel title="Deployment constraint"><div className="callout warning-callout"><Shield size={18}/><span>The inspected FastAPI app does not install CORS middleware. The included Vite development proxy avoids that locally. For deployment, serve the frontend and API behind one origin/reverse proxy, or add an explicit CORS policy in the backend.</span></div></Panel>
      </div>
    </div>
  );
}
