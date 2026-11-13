import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Bot,
  Boxes,
  FlaskConical,
  Gauge,
  Menu,
  Network,
  RefreshCw,
  Settings as SettingsIcon,
  ShieldCheck,
  X,
} from 'lucide-react';
import { api } from './api/client';
import type { AgentEvent, Athlete, HealthStatus, JobRecord, Plan, ReconcileResult } from './api/types';
import type { AppActions, AppData } from './appTypes';
import { AthleteGate } from './components/AthleteGate';
import { Loading } from './components/Loading';
import { StatusBadge } from './components/StatusBadge';
import { loadActiveAthleteId, loadTrackedJobIds, saveActiveAthleteId, saveTrackedJobIds } from './lib/storage';
import { ActivityView } from './views/ActivityView';
import { Jobs } from './views/Jobs';
import { MLRegistry } from './views/MLRegistry';
import { Overview } from './views/Overview';
import { Plans } from './views/Plans';
import { Settings } from './views/Settings';
import { Simulator } from './views/Simulator';
import { Verification } from './views/Verification';

const navItems = [
  { id: 'overview', label: 'Overview', icon: Gauge },
  { id: 'plans', label: 'Plans', icon: Boxes },
  { id: 'verification', label: 'Verification', icon: ShieldCheck },
  { id: 'activity', label: 'Activity', icon: Activity },
  { id: 'simulator', label: 'Simulator', icon: FlaskConical },
  { id: 'jobs', label: 'Jobs', icon: Network },
  { id: 'ml', label: 'ML registry', icon: Bot },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
] as const;

type ViewId = (typeof navItems)[number]['id'];

function getInitialView(): ViewId {
  const hash = window.location.hash.replace('#/', '').replace('#', '') as ViewId;
  return navItems.some((item) => item.id === hash) ? hash : 'overview';
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error';
}

export default function App() {
  const [view, setView] = useState<ViewId>(getInitialView);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [athlete, setAthlete] = useState<Athlete | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [health, setHealth] = useState<HealthStatus>({ live: 'checking', ready: 'checking' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastReconcile, setLastReconcile] = useState<ReconcileResult | null>(null);
  const [trackedJobs, setTrackedJobs] = useState<JobRecord[]>([]);
  const [trackedJobIds, setTrackedJobIds] = useState<string[]>(loadTrackedJobIds);

  const checkHealth = useCallback(async () => {
    const [live, ready] = await Promise.allSettled([api.healthLive(), api.healthReady()]);
    setHealth({
      live: live.status === 'fulfilled' && live.value.status === 'ok' ? 'ok' : 'error',
      ready: ready.status === 'fulfilled' && ready.value.status === 'ready' ? 'ready' : 'error',
    });
  }, []);

  const loadAthleteBundle = useCallback(async (athleteId: string, showSpinner = true) => {
    if (!athleteId) {
      setAthlete(null);
      setPlans([]);
      setEvents([]);
      return;
    }
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      const [athleteResult, plansResult, eventsResult] = await Promise.all([
        api.getAthlete(athleteId),
        api.listPlans(athleteId),
        api.events(athleteId),
      ]);
      setAthlete(athleteResult);
      setPlans(plansResult);
      setEvents(eventsResult);
      saveActiveAthleteId(athleteId);
    } catch (err) {
      setError(errorMessage(err));
      throw err;
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  const refreshJobs = useCallback(async () => {
    if (!trackedJobIds.length) {
      setTrackedJobs([]);
      return;
    }
    const rows = await Promise.all(
      trackedJobIds.map(async (id) => {
        try {
          return await api.getJob(id);
        } catch {
          return null;
        }
      }),
    );
    setTrackedJobs(rows.filter((row): row is JobRecord => row !== null));
  }, [trackedJobIds]);

  useEffect(() => {
    const boot = async () => {
      await checkHealth();
      const activeId = loadActiveAthleteId();
      if (activeId) {
        try {
          await loadAthleteBundle(activeId, false);
        } catch {
          saveActiveAthleteId('');
          setAthlete(null);
        }
      }
      setLoading(false);
    };
    void boot();
  }, [checkHealth, loadAthleteBundle]);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    const onHash = () => setView(getInitialView());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const actions: AppActions = useMemo(() => ({
    setActiveAthlete: async (athleteId) => {
      await loadAthleteBundle(athleteId);
      setView('overview');
      window.location.hash = '/overview';
    },
    bootstrapAthlete: async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.bootstrap();
        await loadAthleteBundle(result.athlete.id, false);
        setView('overview');
        window.location.hash = '/overview';
      } catch (err) {
        setError(errorMessage(err));
        throw err;
      } finally {
        setLoading(false);
      }
    },
    createAthlete: async (payload) => {
      setLoading(true);
      setError(null);
      try {
        const created = await api.createAthlete(payload);
        await loadAthleteBundle(created.id, false);
        setView('overview');
        window.location.hash = '/overview';
      } catch (err) {
        setError(errorMessage(err));
        throw err;
      } finally {
        setLoading(false);
      }
    },
    refresh: async () => {
      try {
        await checkHealth();
        if (athlete) await loadAthleteBundle(athlete.id, false);
      } catch (err) {
        setError(errorMessage(err));
      }
    },
    reconcile: async (reason) => {
      if (!athlete) throw new Error('No active athlete');
      setError(null);
      try {
        const result = await api.reconcile(athlete.id, reason);
        setLastReconcile(result);
        await loadAthleteBundle(athlete.id, false);
        return result;
      } catch (err) {
        setError(errorMessage(err));
        throw err;
      }
    },
    reconcileAsync: async (reason) => {
      if (!athlete) throw new Error('No active athlete');
      setError(null);
      try {
        const result = await api.reconcileAsync(athlete.id, reason);
        const ids = [result.job_id, ...trackedJobIds.filter((id) => id !== result.job_id)];
        setTrackedJobIds(ids);
        saveTrackedJobIds(ids);
        const job = await api.getJob(result.job_id);
        setTrackedJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
        return result.job_id;
      } catch (err) {
        setError(errorMessage(err));
        throw err;
      }
    },
    refreshJobs,
    trackJob: async (jobId) => {
      setError(null);
      try {
        const job = await api.getJob(jobId);
        const ids = [jobId, ...trackedJobIds.filter((id) => id !== jobId)];
        setTrackedJobIds(ids);
        saveTrackedJobIds(ids);
        setTrackedJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
      } catch (err) {
        setError(errorMessage(err));
        throw err;
      }
    },
    removeJob: (jobId) => {
      const ids = trackedJobIds.filter((id) => id !== jobId);
      setTrackedJobIds(ids);
      saveTrackedJobIds(ids);
      setTrackedJobs((current) => current.filter((item) => item.id !== jobId));
    },
    clearError: () => setError(null),
  }), [athlete, checkHealth, loadAthleteBundle, refreshJobs, trackedJobIds]);

  const data: AppData = {
    athlete,
    plans,
    events,
    health,
    loading,
    error,
    lastReconcile,
    trackedJobs,
  };

  const selectView = (id: ViewId) => {
    setView(id);
    window.location.hash = `/${id}`;
    setSidebarOpen(false);
  };

  const disconnect = () => {
    saveActiveAthleteId('');
    setAthlete(null);
    setPlans([]);
    setEvents([]);
    setLastReconcile(null);
  };

  let content;
  if (!athlete && view !== 'settings' && view !== 'ml') {
    content = <AthleteGate actions={actions} />;
  } else {
    switch (view) {
      case 'plans': content = <Plans data={data} />; break;
      case 'verification': content = <Verification data={data} />; break;
      case 'activity': content = <ActivityView data={data} />; break;
      case 'simulator': content = <Simulator data={data} actions={actions} />; break;
      case 'jobs': content = <Jobs data={data} actions={actions} />; break;
      case 'ml': content = <MLRegistry />; break;
      case 'settings': content = <Settings />; break;
      default: content = <Overview data={data} />;
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">A</div>
          <div><strong>APEX</strong><span>AthleteOps Console</span></div>
        </div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => selectView(item.id)}><Icon size={18}/><span>{item.label}</span></button>;
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="health-line"><span>API</span><StatusBadge status={health.live}/></div>
          <div className="health-line"><span>DB ready</span><StatusBadge status={health.ready}/></div>
        </div>
      </aside>
      {sidebarOpen && <button className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"/>}

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Menu size={20}/></button>
          <div className="topbar-athlete">
            {athlete ? <><strong>{athlete.name}</strong><span>{athlete.timezone_name}</span></> : <><strong>No active athlete</strong><span>Select, bootstrap, or create one</span></>}
          </div>
          <div className="topbar-actions">
            {athlete && <button className="btn btn-ghost compact" onClick={() => void actions.refresh()}><RefreshCw size={15}/>Refresh</button>}
            {athlete && <button className="btn btn-ghost compact" onClick={disconnect}>Switch athlete</button>}
          </div>
        </header>

        {error && <div className="error-banner"><span>{error}</span><button onClick={actions.clearError} aria-label="Dismiss error"><X size={17}/></button></div>}

        <div className="page-container">
          {loading ? <Loading label="Loading AthleteOps data"/> : content}
        </div>
      </main>
    </div>
  );
}
