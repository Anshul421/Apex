from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.storage.models import MLExperiment, MLModelVersion, MLRun


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExperimentTracker:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_experiment(self, name: str, description: str = '') -> MLExperiment:
        row = self.db.scalar(select(MLExperiment).where(MLExperiment.name == name))
        if row:
            return row
        row = MLExperiment(name=name, description=description)
        self.db.add(row)
        self.db.flush()
        return row

    def start_run(
        self,
        *,
        experiment: MLExperiment,
        run_name: str,
        code_version: str,
        dataset_name: str,
        dataset_version: str,
        dataset_sha256: str,
        feature_schema_version: str,
        random_seed: int,
        params: dict[str, Any],
        tags: dict[str, Any] | None = None,
    ) -> MLRun:
        run = MLRun(
            experiment_id=experiment.id,
            run_name=run_name,
            status='running',
            code_version=code_version,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            dataset_sha256=dataset_sha256,
            feature_schema_version=feature_schema_version,
            random_seed=random_seed,
            params=params,
            metrics={},
            tags=tags or {},
        )
        self.db.add(run)
        self.db.flush()
        return run

    def finish_run(
        self,
        run: MLRun,
        *,
        metrics: dict[str, Any],
        artifact_uri: str,
        selected_model: str,
        decision: str,
    ) -> MLRun:
        run.metrics = metrics
        run.artifact_uri = artifact_uri
        run.selected_model = selected_model
        run.decision = decision
        run.status = 'finished'
        run.ended_at = utcnow()
        self.db.flush()
        return run

    def fail_run(self, run: MLRun, error: str) -> None:
        run.status = 'failed'
        run.decision = error
        run.ended_at = utcnow()
        self.db.flush()

    def register_model(
        self,
        *,
        name: str,
        run: MLRun,
        artifact_uri: str,
        input_schema: dict[str, Any],
        metrics: dict[str, Any],
        stage: str = 'candidate',
        alias: str | None = 'candidate',
    ) -> MLModelVersion:
        latest = self.db.scalar(
            select(MLModelVersion)
            .where(MLModelVersion.name == name)
            .order_by(desc(MLModelVersion.version))
            .limit(1)
        )
        version = 1 if latest is None else latest.version + 1

        if alias:
            existing_alias = self.db.scalar(
                select(MLModelVersion).where(
                    MLModelVersion.name == name,
                    MLModelVersion.alias == alias,
                )
            )
            if existing_alias:
                existing_alias.alias = None
                self.db.flush()

        row = MLModelVersion(
            name=name,
            version=version,
            run_id=run.id,
            stage=stage,
            alias=alias,
            artifact_uri=artifact_uri,
            model_format='joblib',
            input_schema=input_schema,
            metrics=metrics,
        )
        self.db.add(row)
        self.db.flush()
        return row
