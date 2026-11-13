# APEX AthleteOps Frontend

Frontend-only operations console generated from the inspected `APEX_final_work` backend contracts.

## What it covers

- Athlete selection, simulator bootstrap, and athlete creation.
- Backend liveness/readiness status.
- Current plan overview from live API data.
- Immutable plan-version history and machine-readable revision diffs.
- Session schedules, load/intensity/facility/status fields.
- Constraint results and independent verification history/snapshots.
- Agent event timeline including world observations, intent, optimizer results, web facts, booking/calendar receipts, failures, and replans when those events are emitted.
- Simulator injectors already implemented by the backend.
- Synchronous and asynchronous reconciliation.
- Local tracking of async job IDs because the backend exposes `GET /jobs/{job_id}` but no list-jobs route.
- ML registry capability page that deliberately does not show fabricated/build-time metrics because the current API router exposes no ML read endpoints.

## No hard-coded operational data

The UI does not embed demo athlete metrics, session values, model metrics, plan data, or job results. Runtime values are read from FastAPI. For optional request fields, blank inputs allow backend defaults to apply.

## Local development

```bash
npm install
npm run dev
```

By default Vite proxies `/api` to `http://localhost:8000`, so the frontend can call `/api/v1` without requiring FastAPI CORS middleware during local development.

Copy `.env.example` to `.env` only if you need to override the API target or provide explicit development/OIDC credentials.

## Production note

The inspected FastAPI `app/main.py` does not install CORS middleware. The safest minimal deployment is to serve this frontend and FastAPI behind the same origin/reverse proxy, keeping the frontend API base as `/api/v1`. If the frontend is hosted on a separate origin, the backend must add an explicit CORS policy.

## Backend gaps reflected honestly in the UI

The backend repository contains PostgreSQL models for `ml_experiments`, `ml_runs`, and `ml_model_versions`, but `app/api/routes.py` does not expose REST read routes for them. The frontend therefore leaves the ML registry as an unavailable capability boundary rather than treating repository JSON artifacts as live API state.

Likewise, the backend exposes athlete creation and get-by-ID but no tenant-scoped athlete listing route. The frontend supports known athlete IDs, bootstrap, and creation and stores the active athlete ID locally.

## Build

```bash
npm run typecheck
npm run build
```

The production output is generated in `dist/`.
