"""Repeatable CPU-only classification exercise using invented labels."""

from functools import lru_cache
from typing import Any

import numpy as np
from scipy.optimize import minimize  # type: ignore[import-untyped]
from scipy.special import expit  # type: ignore[import-untyped]

FEATURES = ("page_count", "character_count", "section_count", "reference_count")
PAPER_MODEL_VERSIONS = {"synthetic-logistic-v1": 1.0, "synthetic-logistic-v2": 8.0}


def synthetic_samples(seed: int, count: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    pages = rng.integers(1, 81, count)
    characters = pages * rng.integers(80, 501, count)
    sections = rng.integers(1, 21, count)
    references = rng.integers(0, 101, count)
    values = np.column_stack((pages, characters, sections, references))
    tendency = 0.035 * references + 0.12 * sections + 0.015 * pages - 3.5
    labels = (rng.random(count) < expit(tendency)).astype(int)
    return values, labels


@lru_cache(maxsize=len(PAPER_MODEL_VERSIONS))
def train_demo(model_version: str = "synthetic-logistic-v1") -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, int]]:
    regularization = PAPER_MODEL_VERSIONS[model_version]
    train, labels = synthetic_samples(314, 240)
    holdout, expected = synthetic_samples(159, 80)
    center, scale = train.mean(axis=0), train.std(axis=0)
    design = np.column_stack((np.ones(len(train)), (train - center) / scale))

    def objective(weights: np.ndarray) -> tuple[float, np.ndarray]:
        logits = design @ weights
        penalty = weights.copy()
        penalty[0] = 0
        loss = np.logaddexp(0, logits).sum() - labels @ logits + regularization * (penalty @ penalty) / 2
        return float(loss), design.T @ (expit(logits) - labels) + regularization * penalty

    fitted = minimize(objective, np.zeros(len(FEATURES) + 1), jac=True, method="BFGS")
    if not fitted.success:
        raise RuntimeError("Synthetic classifier did not converge")
    weights = fitted.x
    predicted = (weights[0] + (holdout - center) / scale @ weights[1:] >= 0).astype(int)
    validation = {
        "training_count": len(train),
        "holdout_count": len(holdout),
        "correct": int(np.count_nonzero(predicted == expected)),
        "false_positive": int(np.count_nonzero((predicted == 1) & (expected == 0))),
        "false_negative": int(np.count_nonzero((predicted == 0) & (expected == 1))),
    }
    return weights, center, scale, validation


def classifier_artifact(model_version: str) -> dict[str, Any]:
    weights, center, scale, validation = train_demo(model_version)
    return {"weights": weights.tolist(), "center": center.tolist(), "scale": scale.tolist(),
            "validation": validation,
            "recipe": {"algorithm": "L2 logistic regression", "l2": PAPER_MODEL_VERSIONS[model_version],
                       "training_seed": 314, "holdout_seed": 159}}


def classify_demo(
    result: dict[str, Any], model_version: str, artifact: dict[str, Any],
) -> dict[str, Any]:
    inputs = {key: result.get(key) for key in FEATURES}
    missing = [key for key, value in inputs.items() if value is None]
    probability = None
    if not missing:
        values = np.asarray(list(inputs.values()), dtype=float)
        weights = np.asarray(artifact["weights"])
        probability = float(expit(weights[0] + ((values - artifact["center"]) / artifact["scale"]) @ weights[1:]))
    return {
        "model_version": model_version,
        "recipe": artifact["recipe"],
        "inputs": inputs,
        "missing": missing,
        "score": probability,
        "label": None if probability is None else "模拟优秀类" if probability >= 0.5 else "模拟普通类",
        "validation": artifact["validation"],
    }
