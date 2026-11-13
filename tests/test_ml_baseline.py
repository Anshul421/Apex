from __future__ import annotations

import json
from pathlib import Path

import joblib
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.ml.data import FEATURE_COLUMNS, TARGET_COLUMN, TIME_COLUMN, generate_synthetic_recovery_dataset
from app.ml.training import run_baseline_experiment
from app.storage.database import Base
from app.storage.models import MLExperiment, MLModelVersion, MLRun


def test_synthetic_ml_dataset_is_deterministic():
    first = generate_synthetic_recovery_dataset(n_samples=128, seed=42)
    second = generate_synthetic_recovery_dataset(n_samples=128, seed=42)

    assert list(first.columns) == [TIME_COLUMN, *FEATURE_COLUMNS, TARGET_COLUMN]
    assert first.equals(second)
    assert set(first[TARGET_COLUMN].unique()).issubset({0, 1})


def test_baseline_experiment_tracks_run_and_registry(tmp_path: Path):
    db_path = tmp_path / 'ml_tracking.db'
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)

    settings = Settings(
        _env_file=None,
        database_url=f'sqlite:///{db_path}',
        ml_artifact_dir=str(tmp_path / 'artifacts'),
        ml_random_seed=42,
        ml_min_auc_lift=0.02,
        llm_provider='rule_based',
    )

    with Session(engine) as db:
        result = run_baseline_experiment(settings, n_samples=1200, db=db)

        run = db.get(MLRun, result['run_id'])
        model = db.scalar(select(MLModelVersion).where(MLModelVersion.run_id == run.id))
        experiment = db.get(MLExperiment, run.experiment_id)

        assert run.status == 'finished'
        assert experiment.name == settings.ml_experiment_name
        assert result['selected_model'] in {'logistic_regression', 'random_forest'}
        assert result['metrics']['selected_auc_lift_over_heuristic'] > 0
        assert Path(model.artifact_uri).exists()
        assert model.model_format == 'joblib'
        loaded = joblib.load(model.artifact_uri)
        assert hasattr(loaded, 'predict_proba')
        assert len(run.dataset_sha256) == 64

        manifest = json.loads((Path(result['artifact_dir']) / 'run_manifest.json').read_text())
        assert manifest['run_id'] == run.id
        assert manifest['dataset_sha256'] == run.dataset_sha256


def test_model_registry_moves_candidate_alias(tmp_path: Path):
    db_path = tmp_path / 'ml_registry.db'
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        database_url=f'sqlite:///{db_path}',
        ml_artifact_dir=str(tmp_path / 'artifacts'),
        ml_random_seed=42,
        llm_provider='rule_based',
    )

    with Session(engine) as db:
        first = run_baseline_experiment(settings, n_samples=900, db=db)
        second = run_baseline_experiment(settings, n_samples=900, db=db)
        candidates = list(
            db.scalars(
                select(MLModelVersion).where(
                    MLModelVersion.name == settings.ml_model_name,
                    MLModelVersion.alias == 'candidate',
                )
            ).all()
        )

        assert first['registered_model']['version'] == 1
        assert second['registered_model']['version'] == 2
        assert len(candidates) <= 1
