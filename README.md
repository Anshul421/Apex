# APEX

**APEX — Autonomous Athlete Performance Planner**

APEX is an agentic AI system designed to continuously build, evaluate, and adapt an athlete's training plan using performance data, wellness information, scheduling constraints, and recovery signals.

Unlike a traditional fitness chatbot that simply generates a workout plan, APEX operates as a goal-driven agent. It observes changes in athlete state, reasons about their impact, modifies the plan when required, verifies whether the new plan satisfies constraints, and preserves state across planning cycles.

---

## What APEX Does

APEX follows an agentic planning loop:

```text
Athlete Data
     │
     ▼
Wellness / Performance / Schedule Inputs
     │
     ▼
Structured Intent + State Interpretation
     │
     ▼
LangGraph Agent Orchestration
     │
     ├──► Constraint Analysis
     │
     ├──► Training Load Analysis
     │
     ├──► Recovery Analysis
     │
     └──► Planning Decision
              │
              ▼
        Schedule Optimizer
          OR-Tools
              │
              ▼
        Candidate Training Plan
              │
              ▼
        Deterministic Verification
              │
        ┌─────┴─────┐
        │           │
      Valid       Invalid
        │           │
        │           └──► Replan
        ▼
Persist Plan + Agent State
        │
        ▼
PostgreSQL / LangGraph Checkpoints
```

---

## Core Idea

APEX treats athlete planning as a continuously changing optimization problem rather than a one-time workout-generation task.

For example, an athlete may begin the day with a planned high-intensity training session.

Later, the system may receive updated information such as:

- reduced recovery score
- increased fatigue
- schedule changes
- missed sessions
- unexpected training load
- performance deterioration

APEX can evaluate the new state and determine whether the current plan is still feasible.

If not, it can generate a revised schedule and verify it before accepting the change.

---

## Agentic Architecture

The system is built around a LangGraph-based state machine.

The orchestration layer manages a loop similar to:

```text
Observe
   ↓
Interpret
   ↓
Plan
   ↓
Execute
   ↓
Verify
   ↓
Persist
   ↓
Observe Again
```

Each stage has a clearly defined responsibility.

### Observation

Collects athlete state such as:

- recovery
- fatigue
- training history
- performance
- availability
- scheduling constraints

### Interpretation

Converts incoming information into structured state that the planning system can use.

LLM reasoning can assist with interpreting natural-language goals and requests, while critical scheduling constraints remain deterministic.

### Planning

Determines whether the current training plan should remain unchanged or requires modification.

### Optimization

OR-Tools is used to solve scheduling and constraint problems.

Possible constraints include:

- available training windows
- recovery requirements
- session duration
- training frequency
- workload limits
- scheduling conflicts

### Verification

Generated plans are checked before being accepted.

This prevents the AI planning layer from directly producing an invalid operational schedule.

### Persistence

Agent state and planning history are persisted so that future decisions can use previous observations and actions rather than treating every request as a completely new conversation.

---

## Technology Stack

### Backend

- Python
- FastAPI
- Pydantic
- Uvicorn
- SQLAlchemy
- Alembic

### Agent Orchestration

- LangGraph
- LangGraph checkpointing
- Structured LLM outputs

### Optimization

- Google OR-Tools

### Database

- PostgreSQL
- SQLite for local/checkpoint workflows where applicable

### AI / LLM

The architecture supports external LLM providers through a structured planning layer.

The LLM is used for interpretation and reasoning rather than being trusted as the sole authority for deterministic constraints.

### Observability

- OpenTelemetry
- FastAPI instrumentation

### Testing

- Pytest
- Playwright

### Infrastructure

- Docker
- Docker Compose

---

## Project Structure

```text
APEX/
│
├── alembic/
│   └── Database migrations
│
├── app/
│   └── Main backend application
│
├── artifacts/
│   └── Generated experiment and application artifacts
│
├── evaluator/
│   └── Evaluation logic
│
├── frontend/
│   └── Frontend application
│
├── scripts/
│   └── Development and utility scripts
│
├── simulator/
│   └── Athlete/environment simulation tools
│
├── tests/
│   └── Automated tests
│
├── .env.example
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── POSTGRES_SCHEMA.sql
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Why APEX Is Agentic

APEX is designed to go beyond a request-response chatbot.

The system includes:

### Goal-Driven Behaviour

The agent works toward athlete performance and training objectives instead of merely answering isolated prompts.

### Persistent State

Previous planning decisions and athlete state can be retained across agent executions.

### Tool Interaction

The agent can use specialized components such as:

- scheduling tools
- optimization engines
- databases
- athlete-data services
- external information sources

### Action → Observation → Replanning

APEX can react to changes after a plan has already been created.

```text
Plan
 ↓
New Athlete Observation
 ↓
Detect Meaningful Change
 ↓
Evaluate Existing Plan
 ↓
Reconcile Constraints
 ↓
Generate Updated Plan
 ↓
Verify
```

### Deterministic Verification

Critical constraints are verified using deterministic logic instead of relying entirely on LLM output.

This separates:

```text
AI reasoning
```

from:

```text
Operational validity
```

---

## Example Scenario

Suppose an athlete initially has:

```text
Recovery Score: 0.82
Fatigue: 1
Planned Session: High-intensity training
```

Later, a wellness update arrives:

```text
Recovery Score: 0.35
Fatigue: 4
```

Instead of continuing with the original plan blindly, APEX can:

1. ingest the new wellness state
2. compare it with the previous state
3. identify that the existing plan may violate recovery constraints
4. invoke the reconciliation workflow
5. generate an alternative schedule
6. verify that the updated schedule is feasible
7. persist the new plan and agent state

This demonstrates a genuine:

```text
Observation → Reasoning → Action → Verification → Replanning
```

agent loop.

---

## Getting Started

### 1. Clone the Repository

```bash
git clone YOUR_REPOSITORY_URL
cd APEX
```

---

### 2. Create a Virtual Environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Configure Environment Variables

Copy:

```text
.env.example
```

to:

```text
.env
```

Windows:

```bash
copy .env.example .env
```

Linux / macOS:

```bash
cp .env.example .env
```

Add the required database and AI-provider configuration to `.env`.

Never commit `.env` to GitHub.

---

## Running with Docker

Start the required services:

```bash
docker compose up -d
```

Check running containers:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f
```

Stop the services:

```bash
docker compose down
```

---

## Database Migrations

Run Alembic migrations with:

```bash
alembic upgrade head
```

Create a new migration:

```bash
alembic revision --autogenerate -m "migration description"
```

---

## Run the API

For local development:

```bash
uvicorn app.main:app --reload
```

The API will normally be available at:

```text
http://127.0.0.1:8000
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Run Tests

```bash
pytest
```

For more detailed output:

```bash
pytest -v
```

---

## System Design Principle

One of the main design decisions in APEX is separating **reasoning** from **verification**.

The LLM may propose or interpret a decision, but deterministic components remain responsible for enforcing critical rules.

```text
LLM
 │
 │ proposes / interprets
 ▼
Structured Plan
 │
 ▼
Constraint Engine
 │
 ▼
Optimizer
 │
 ▼
Verification
 │
 ├── Invalid → Replan
 │
 └── Valid → Persist
```

This makes the agent more inspectable and reduces dependence on unrestricted LLM-generated decisions.

---

## Current Capabilities

APEX currently focuses on:

- LangGraph-based orchestration
- persistent agent checkpoints
- deterministic training constraints
- training-load evaluation
- schedule reconciliation
- plan verification
- athlete-state simulation
- PostgreSQL integration
- ML baseline experimentation
- API-based architecture
- automated testing
- Docker-based deployment environment

---

## Future Development

Potential extensions include:

- live wearable-device integration
- richer athlete performance models
- injury-risk estimation
- competition-aware periodization
- nutrition planning tools
- real-time schedule adaptation
- expanded ML prediction models
- external sports-data integrations
- richer agent tool selection
- advanced observability and tracing
- long-term athlete-state modelling

---

## Design Philosophy

APEX follows a simple principle:

> AI can reason about what should happen, but critical constraints should still be independently verified before an action becomes part of the athlete's plan.

The goal is to create an autonomous planning system that remains inspectable, testable, and operationally reliable.

---

## License

Add the appropriate project license before production or public distribution.