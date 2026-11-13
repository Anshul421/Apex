from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def classification_metrics(y_true, y_pred, y_score) -> dict[str, float]:
    return {
        'accuracy': float(accuracy_score(y_true, y_pred)),
        'precision': float(precision_score(y_true, y_pred, zero_division=0)),
        'recall': float(recall_score(y_true, y_pred, zero_division=0)),
        'f1': float(f1_score(y_true, y_pred, zero_division=0)),
        'roc_auc': float(roc_auc_score(y_true, y_score)),
        'brier': float(brier_score_loss(y_true, y_score)),
        'positive_rate': float(np.mean(y_pred)),
    }


def heuristic_scores(frame) -> tuple[np.ndarray, np.ndarray]:
    prediction = (
        (frame['recovery_score'] < 0.45)
        | (frame['fatigue'] >= 4)
        | (
            (frame['hours_to_match'] < 48)
            & (frame['high_intensity_last_48h'] == 1)
        )
    ).astype(int)

    score = np.clip(
        (1.0 - frame['recovery_score'].to_numpy()) * 0.45
        + ((frame['fatigue'].to_numpy() - 1) / 4.0) * 0.25
        + ((frame['soreness'].to_numpy() - 1) / 4.0) * 0.10
        + frame['high_intensity_last_48h'].to_numpy() * 0.10
        + (frame['hours_to_match'].to_numpy() < 48).astype(float) * 0.10,
        0.0,
        1.0,
    )
    return prediction.to_numpy(), score
