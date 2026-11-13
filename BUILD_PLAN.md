# AthleteOps Backend Build Plan

This build order follows the project blueprint's dependency graph and the backend/ML requirements: start with deterministic state and constraints, add agent semantics only after the system can independently verify correctness, and postpone ML/platform complexity until there is a measured need.

## Step 1 - Establish the modular backend foundation - DONE

**Action**
- FastAPI versioned REST API under `/api/v1`.
- SQLAlchemy 2.0 persistence with PostgreSQL as the production default.
- Alembic migration for the initial schema.
- Generic OIDC/JWT verification with development-only header auth.
- Correlation/request IDs and optional OpenTelemetry instrumentation.
- Dockerfile + Docker Compose for API, worker, and PostgreSQL.

**Reason**
The backend/ML plan recommends a modular monolith first, a relational system of record, an external identity provider, versioned APIs, and observability. For a 10-15-user demo, splitting this into microservices would add failure modes without adding product value.

**Acceptance check**
- Database migration upgrades and downgrades successfully.
- Health/readiness endpoints exist.
- Tenant-scoped athlete access is enforced at API lookup boundaries.

## Step 2 - Build persistent, event-oriented AthleteOps state - DONE

**Action**
Persist:
- athletes and objectives;
- observations with source versions and observation timestamps;
- match revisions;
- immutable plan versions with parent links, reasons, world-state hashes, and machine-readable diffs;
- sessions;
- deterministic constraint results;
- tool actions and receipts;
- web evidence;
- verification runs;
- calendar entries and facility bookings;
- agent timeline events;
- asynchronous jobs.

**Reason**
The AthleteOps design explicitly requires plan V1 -> V2 -> V3 history, action receipts, and end-state verification. Overwriting one `current_plan` row would destroy the evidence required to diagnose and demonstrate replanning.

**Acceptance check**
Every revision is a new row; prior plans remain inspectable.

## Step 3 - Build the synthetic world/state APIs - DONE

**Action**
- Demo bootstrap creates synthetic GPS history, wellness, athlete availability, match state, and facility slots.
- Failure/change injectors support wellness drop, match move, booking conflict, stale GPS, and an infeasible availability state.

**Reason**
The build blueprint says the first dependency is synthetic state APIs. They make agent behavior deterministic and testable before real third-party integrations are introduced.

**Acceptance check**
Each injected change produces a new source/version record instead of mutating history invisibly.

## Step 4 - Implement the deterministic load adapter - DONE

**Action**
- `SyntheticLoadAdapter` computes daily/rolling load checks and match-spacing checks.
- Evaluator thresholds are configuration, not hard-coded medical claims.
- The interface is replaceable by the competition's supplied load-management algorithm.

**Reason**
The LLM must not decide whether load is "safe". The blueprint explicitly makes the event evaluator authoritative and replaceable.

**Acceptance check**
A deliberately excessive session load is caught by the independent verifier.

## Step 5 - Implement constraint optimization - DONE, with one runtime caveat

**Action**
- `ConstraintOptimizer` is wired to OR-Tools CP-SAT when OR-Tools is installed.
- It enforces one candidate per required session, no overlaps, athlete availability, match-spacing, daily/rolling workload limits, and a minimum-disruption objective.
- An equivalent deterministic branch-and-bound fallback is included only so the repository can be tested in an offline environment where OR-Tools cannot be installed.

**Reason**
The blueprint separates semantic intent from feasibility. A solver, not the LLM, decides whether the requested schedule is feasible.

**Acceptance check**
The optimizer returns `INFEASIBLE` when no legal schedule exists rather than fabricating a plan.

## Step 6 - Implement independent verification - DONE

**Action**
The verifier reconstructs checks from the stored plan plus the current source snapshot:
- world-state hash / stale-plan check;
- source freshness;
- deterministic load constraints;
- session overlap;
- athlete availability;
- booking confirmation;
- calendar synchronization;
- outstanding action count.

**Reason**
The project requires end-state correctness, not an LLM saying that it succeeded. Verification therefore uses no planner self-assessment.

**Acceptance check**
Tampering with a plan causes deterministic verification failure.

## Step 7 - Implement plan versioning and receding-horizon repair - DONE

**Action**
- Completed sessions are frozen.
- Parent-plan sessions are preserved when still valid.
- Changes are scored with a churn penalty so the solver changes the smallest feasible part of the plan.
- Every plan stores a fingerprint of the exact GPS/wellness/fixture/availability/load-algorithm versions used to create it.

**Reason**
This addresses the project's niche problem: one local schedule edit can cascade into future workload, availability, match-proximity, and booking violations.

**Acceptance check**
A wellness change updates the affected sessions while preserving unaffected sessions; a fixture move creates a new world hash and repairs only the affected horizon.

## Step 8 - Implement the closed-loop orchestrator - DONE for the deterministic baseline

**Action**
The loop is:

`observe -> semantic intent -> candidates -> optimize -> pre-verify -> act -> observe receipts -> final verify -> repair if needed`

The current intent provider is rule-based so that backend correctness does not depend on an LLM. `app/agent/prompts.py` and `app/agent/graph.py` define the strict structured-intent contract and LangGraph topology for the next integration step.

**Reason**
The backend/ML plan explicitly says to prove the deterministic baseline first, while the AthleteOps blueprint says one stateful orchestrator is preferable to a collection of chatty agents.

**Acceptance check**
Repeated reconcile against an unchanged world is a no-op rather than producing another plan version.

## Step 9 - Implement real action semantics and failure recovery - DONE in sandbox adapters

**Action**
- Calendar writes create/update persistent calendar events using idempotency keys.
- Booking actions persist confirmations and can return a deliberate conflict.
- A booking conflict is observed, persisted, the failed plan is invalidated, the changed facility state is versioned, and the agent replans to an alternative facility.
- Tool calls are logged as receipts.

**Reason**
The events require action followed by observation and recovery, not merely a generated plan.

**Acceptance check**
The booking-conflict test creates an invalidated intermediate plan and a later verified plan using a different facility at the same intended time.

## Step 10 - Isolate untrusted web content - DONE at the backend policy boundary

**Action**
- Browser-derived information is normalized into allow-listed `WebFact` fields.
- The state-changing tools consume structured state/policy, not arbitrary page instructions.
- A Playwright adapter is scaffolded for real browsing.

**Reason**
The blueprint explicitly requires "web is evidence, not authority" because indirect prompt injection can otherwise cross into tool execution.

**Acceptance check**
An external field named `system_instruction` is rejected by the web-data policy.

## Step 11 - Add asynchronous execution - DONE for small scale

**Action**
- A database-backed job queue and separate worker process can run reconciliation asynchronously.
- Retries use bounded attempts and dead-letter state.

**Reason**
The backend plan requires asynchronous workers. For 10-15 users, a PostgreSQL-backed queue avoids introducing Redis/Kafka before throughput demonstrates a need. Redis remains intentionally absent because no cache has yet proven useful.

**Acceptance check**
The API can enqueue a job and a separate worker can process it without changing domain logic.

## Step 12 - Automated evaluation - DONE

The test suite covers:
1. baseline planning/execution;
2. wellness-triggered revision;
3. fixture-triggered revision;
4. booking failure and recovery;
5. stale data refusal;
6. independent constraint violation detection;
7. duplicate invocation/idempotency;
8. web-injection isolation;
9. infeasible scheduling;
10. API bootstrap + reconciliation.

Current result: **11/11 tests pass** in the provided build environment.

## Next build slice - NOT falsely marked complete

These are the next steps because they depend on external packages/accounts or event-specific contracts:
- install/run OR-Tools and prove the CP-SAT path rather than the offline fallback;
- wire LangGraph durable checkpoints to PostgreSQL;
- connect a real structured-tool-calling LLM for semantic intent only;
- connect Playwright to an actual allowed booking/venue site;
- connect Google Calendar or the event-provided calendar sandbox;
- add cancellation/compensation for obsolete facility reservations;
- replace synthetic evaluator thresholds with the event's supplied load-management contract;
- switch public deployment from development auth to a real OIDC provider;
- add production OpenTelemetry exporter/alerts;
- only then evaluate whether any actual ML model adds measurable value.
