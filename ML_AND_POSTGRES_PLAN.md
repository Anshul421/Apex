# ML Baseline + Experiment Tracking + PostgreSQL Implementation

## Completed implementation sequence

1. Defined a non-authoritative offline ML target: `needs_load_reduction`.
2. Added deterministic synthetic dataset generation with immutable CSV snapshot + SHA-256 fingerprint.
3. Added a no-ML heuristic baseline.
4. Added scikit-learn logistic-regression and random-forest baselines.
5. Added held-out evaluation metrics: accuracy, precision, recall, F1, ROC-AUC, and Brier score.
6. Added automatic candidate selection by ROC-AUC and an explicit minimum lift gate over the deterministic heuristic.
7. Added artifact persistence: model.joblib, metrics.json, input_schema.json, run_manifest.json.
8. Added database-backed experiment lineage tables: `ml_experiments`, `ml_runs`, `ml_model_versions`.
9. Added a candidate alias/version registry with lineage to dataset, code version, params, metrics, and artifact URI.
10. Added a second Alembic migration for ML experiment tracking/registry.
11. Switched `.env.example` and Docker Compose to PostgreSQL-first local/dev configuration.
12. Added PostgreSQL connection-pool settings and retained SQLite only for tests/lightweight isolated runs.
13. Added PostgreSQL schema compilation/export (`POSTGRES_SCHEMA.sql`).
14. Added ML + PostgreSQL tests.
