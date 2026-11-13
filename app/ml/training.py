from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.config import Settings, get_settings
from app.ml.data import FEATURE_COLUMNS, TARGET_COLUMN, materialize_dataset
from app.ml.metrics import classification_metrics, heuristic_scores
from app.ml.tracking import ExperimentTracker
from sqlalchemy.orm import Session

from app.storage.database import Base, SessionLocal, engine


def _code_version() -> str:
    env_sha = os.getenv('GIT_COMMIT_SHA')
    if env_sha:
        return env_sha
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short=12', 'HEAD'],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return 'unversioned-local'


def _input_schema() -> dict[str, Any]:
    return {
        'version': 'recovery-features:v1',
        'features': [
            {'name': 'recovery_score', 'type': 'float', 'range': [0, 1]},
            {'name': 'fatigue', 'type': 'int', 'range': [1, 5]},
            {'name': 'soreness', 'type': 'int', 'range': [1, 5]},
            {'name': 'sleep_quality', 'type': 'int', 'range': [1, 5]},
            {'name': 'acute_load', 'type': 'float'},
            {'name': 'rolling_7d_load', 'type': 'float'},
            {'name': 'hours_to_match', 'type': 'float'},
            {'name': 'high_intensity_last_48h', 'type': 'int', 'range': [0, 1]},
            {'name': 'load_monotony', 'type': 'float'},
        ],
        'target': TARGET_COLUMN,
        'target_semantics': 'synthetic planning-intervention flag; not a medical/injury label',
    }


def run_baseline_experiment(
    settings: Settings | None = None,
    *,
    n_samples: int = 2500,
    db: Session | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    artifact_root = Path(settings.ml_artifact_dir)
    dataset_dir = artifact_root / 'datasets'
    run_dir = artifact_root / 'runs'
    dataset = materialize_dataset(
        dataset_dir,
        settings.ml_dataset_name,
        settings.ml_random_seed,
        n_samples=n_samples,
    )

    frame = dataset.frame
    # Time-aware holdout: the final 25% of the synthetic timeline is reserved
    # for evaluation so model selection never sees future rows.
    split_at = int(len(frame) * 0.75)
    train_frame = frame.iloc[:split_at].copy()
    test_frame = frame.iloc[split_at:].copy()
    X_train = train_frame[FEATURE_COLUMNS]
    y_train = train_frame[TARGET_COLUMN]
    X_test = test_frame[FEATURE_COLUMNS]
    y_test = test_frame[TARGET_COLUMN]
    y = frame[TARGET_COLUMN]

    heuristic_pred, heuristic_score = heuristic_scores(X_test)
    heuristic_metrics = classification_metrics(y_test, heuristic_pred, heuristic_score)

    candidates: dict[str, Any] = {
        'logistic_regression': Pipeline(
            [
                ('scale', StandardScaler()),
                (
                    'model',
                    LogisticRegression(
                        max_iter=1000,
                        random_state=settings.ml_random_seed,
                    ),
                ),
            ]
        ),
        'random_forest': RandomForestClassifier(
            n_estimators=250,
            max_depth=7,
            min_samples_leaf=8,
            class_weight='balanced',
            random_state=settings.ml_random_seed,
            n_jobs=-1,
        ),
    }

    model_metrics: dict[str, dict[str, float]] = {}
    fitted_models: dict[str, Any] = {}
    for name, model in candidates.items():
        model.fit(X_train, y_train)
        probability = model.predict_proba(X_test)[:, 1]
        prediction = (probability >= 0.5).astype(int)
        model_metrics[name] = classification_metrics(y_test, prediction, probability)
        fitted_models[name] = model

    selected_name = max(model_metrics, key=lambda name: model_metrics[name]['roc_auc'])
    selected_metrics = model_metrics[selected_name]
    auc_lift = selected_metrics['roc_auc'] - heuristic_metrics['roc_auc']
    promotes_over_baseline = auc_lift >= settings.ml_min_auc_lift
    decision = (
        f'candidate accepted for further evaluation: ROC-AUC lift={auc_lift:.4f}'
        if promotes_over_baseline
        else f'candidate rejected: ROC-AUC lift={auc_lift:.4f} below required {settings.ml_min_auc_lift:.4f}'
    )

    # Experiment tables are part of Base metadata and therefore work with both
    # SQLite tests and PostgreSQL dev/production.
    owns_db = db is None
    if db is None:
        # SQLite is allowed to self-create for isolated local baseline runs.
        # PostgreSQL development/production must be migrated with Alembic first.
        if settings.database_url.startswith('sqlite'):
            Base.metadata.create_all(engine)
        db = SessionLocal()
    tracker = ExperimentTracker(db)
    experiment = tracker.get_or_create_experiment(
        settings.ml_experiment_name,
        description='Offline baseline for a synthetic planning-intervention target.',
    )
    run_name = f'baseline-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}'
    params = {
        'n_samples': n_samples,
        'holdout': 'chronological_last_25_percent',
        'models': {
            'logistic_regression': {'max_iter': 1000},
            'random_forest': {
                'n_estimators': 250,
                'max_depth': 7,
                'min_samples_leaf': 8,
                'class_weight': 'balanced',
            },
        },
        'selection_metric': 'roc_auc',
        'minimum_auc_lift': settings.ml_min_auc_lift,
    }
    run = tracker.start_run(
        experiment=experiment,
        run_name=run_name,
        code_version=_code_version(),
        dataset_name=settings.ml_dataset_name,
        dataset_version=dataset.version,
        dataset_sha256=dataset.sha256,
        feature_schema_version=settings.ml_feature_schema_version,
        random_seed=settings.ml_random_seed,
        params=params,
        tags={
            'data_origin': 'synthetic',
            'production_authority': 'none',
            'medical_label': False,
            'python': platform.python_version(),
        },
    )

    try:
        artifact_dir = run_dir / run.id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        model_path = artifact_dir / 'model.joblib'
        joblib.dump(fitted_models[selected_name], model_path)

        metrics_payload = {
            'deterministic_heuristic': heuristic_metrics,
            **model_metrics,
            'selected_model': selected_name,
            'selected_auc_lift_over_heuristic': float(auc_lift),
            'meets_minimum_auc_lift': bool(promotes_over_baseline),
            'test_rows': int(len(X_test)),
            'train_rows': int(len(X_train)),
            'class_balance': float(y.mean()),
        }
        (artifact_dir / 'metrics.json').write_text(
            json.dumps(metrics_payload, indent=2, sort_keys=True)
        )
        (artifact_dir / 'input_schema.json').write_text(
            json.dumps(_input_schema(), indent=2, sort_keys=True)
        )
        (artifact_dir / 'run_manifest.json').write_text(
            json.dumps(
                {
                    'run_id': run.id,
                    'experiment_id': experiment.id,
                    'dataset_path': str(dataset.path),
                    'dataset_sha256': dataset.sha256,
                    'dataset_version': dataset.version,
                    'code_version': run.code_version,
                    'selected_model': selected_name,
                    'decision': decision,
                    'params': params,
                },
                indent=2,
                sort_keys=True,
            )
        )

        run = tracker.finish_run(
            run,
            metrics=metrics_payload,
            artifact_uri=str(artifact_dir),
            selected_model=selected_name,
            decision=decision,
        )
        model_version = tracker.register_model(
            name=settings.ml_model_name,
            run=run,
            artifact_uri=str(model_path),
            input_schema=_input_schema(),
            metrics=selected_metrics,
            stage='candidate' if promotes_over_baseline else 'rejected',
            alias='candidate' if promotes_over_baseline else None,
        )
        db.commit()

        result = {
            'experiment_id': experiment.id,
            'run_id': run.id,
            'run_status': run.status,
            'dataset': {
                'name': dataset.path.name,
                'version': dataset.version,
                'sha256': dataset.sha256,
                'rows': int(len(frame)),
            },
            'metrics': metrics_payload,
            'selected_model': selected_name,
            'decision': decision,
            'artifact_dir': str(artifact_dir),
            'registered_model': {
                'name': model_version.name,
                'version': model_version.version,
                'stage': model_version.stage,
                'alias': model_version.alias,
                'artifact_uri': model_version.artifact_uri,
            },
        }
        (artifact_root / 'latest_baseline_result.json').write_text(
            json.dumps(result, indent=2, sort_keys=True)
        )
        return result
    except Exception as exc:
        tracker.fail_run(run, f'{type(exc).__name__}: {exc}')
        db.commit()
        raise
    finally:
        if owns_db:
            db.close()
