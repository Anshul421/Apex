from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    'recovery_score',
    'fatigue',
    'soreness',
    'sleep_quality',
    'acute_load',
    'rolling_7d_load',
    'hours_to_match',
    'high_intensity_last_48h',
    'load_monotony',
]
TARGET_COLUMN = 'needs_load_reduction'
TIME_COLUMN = 'event_time'


@dataclass(frozen=True)
class DatasetArtifact:
    frame: pd.DataFrame
    path: Path
    sha256: str
    version: str


def generate_synthetic_recovery_dataset(
    n_samples: int = 2500,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a deterministic sandbox dataset for planning-intervention prediction.

    This target is a synthetic planning label, not an injury/medical outcome.
    """
    rng = np.random.default_rng(seed)

    recovery = rng.beta(2.3, 2.0, n_samples)
    fatigue = rng.integers(1, 6, n_samples)
    soreness = rng.integers(1, 6, n_samples)
    sleep = rng.integers(1, 6, n_samples)
    acute = np.clip(rng.normal(420, 160, n_samples), 80, 900)
    rolling = np.clip(rng.normal(1900, 600, n_samples), 400, 3800)
    hours = np.clip(rng.gamma(3.0, 35.0, n_samples), 8, 240)
    high_recent = rng.binomial(1, 0.35, n_samples)
    monotony = np.clip(rng.normal(1.4, 0.45, n_samples), 0.5, 3.0)

    risk = (
        2.2 * (1.0 - recovery)
        + 0.40 * (fatigue - 2)
        + 0.34 * (soreness - 2)
        + 0.30 * (3 - sleep)
        + 0.0010 * np.maximum(rolling - 1700, 0)
        + 0.0015 * np.maximum(acute - 500, 0)
        + 0.55 * high_recent
        + 0.90 * (hours < 48)
        + 0.75 * ((recovery < 0.45) & (high_recent == 1))
        + 0.45 * np.maximum(monotony - 1.5, 0)
    )
    logits = risk - 2.6 + rng.normal(0, 0.55, n_samples)
    probability = 1.0 / (1.0 + np.exp(-logits))
    label = rng.binomial(1, probability)

    event_time = pd.date_range(
        start='2025-01-01T00:00:00Z',
        periods=n_samples,
        freq='h',
    )

    return pd.DataFrame(
        {
            TIME_COLUMN: event_time.astype(str),
            'recovery_score': recovery.astype(float),
            'fatigue': fatigue.astype(int),
            'soreness': soreness.astype(int),
            'sleep_quality': sleep.astype(int),
            'acute_load': acute.astype(float),
            'rolling_7d_load': rolling.astype(float),
            'hours_to_match': hours.astype(float),
            'high_intensity_last_48h': high_recent.astype(int),
            'load_monotony': monotony.astype(float),
            TARGET_COLUMN: label.astype(int),
        }
    )


def materialize_dataset(
    output_dir: str | Path,
    dataset_name: str,
    seed: int,
    n_samples: int = 2500,
) -> DatasetArtifact:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    frame = generate_synthetic_recovery_dataset(n_samples=n_samples, seed=seed)
    version = f'v1-seed{seed}-n{n_samples}'
    path = directory / f'{dataset_name}-{version}.csv'
    frame.to_csv(path, index=False, float_format='%.8f')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return DatasetArtifact(frame=frame, path=path, sha256=digest, version=version)
