"""CPU-only clustering exercise using synthetic dimension scores."""

from collections.abc import Callable
from functools import lru_cache
from itertools import pairwise
from typing import Any

import numpy as np
from scipy.cluster.vq import kmeans2  # type: ignore[import-untyped]

DIMENSIONS = ("学术基础", "科研产出", "学术影响")
GROUPS = ("学术基础较强", "科研产出较强", "多维较均衡")
SYNTHETIC_CENTERS = np.asarray(((0.86, 0.38, 0.44), (0.47, 0.88, 0.49), (0.71, 0.71, 0.76)))
STUDENT_MODEL_VERSIONS = ("synthetic-kmeans-v1", "synthetic-autoencoder-v2")


def synthetic_profiles(seed: int, per_group: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    origins = np.repeat(np.arange(len(GROUPS)), per_group)
    profiles = SYNTHETIC_CENTERS[origins] + rng.normal(0, 0.11, (len(origins), len(DIMENSIONS)))
    order = rng.permutation(len(origins))
    return np.clip(profiles[order], 0, 1), origins[order]


@lru_cache(maxsize=1)
def train_student_clusters() -> tuple[np.ndarray, list[str], dict[str, int]]:
    train, origins = synthetic_profiles(29, 80)
    holdout, expected = synthetic_profiles(31, 30)
    centers, assigned = kmeans2(train, len(GROUPS), iter=50, minit="++", rng=np.random.default_rng(37))
    # Cluster names come from the most frequent simulated profile in each
    # training cluster. Holdout labels are used only for the check below.
    mapping = np.asarray([
        np.bincount(origins[assigned == index], minlength=len(GROUPS)).argmax()
        for index in range(len(centers))
    ])
    holdout_groups = ((holdout[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return centers, [GROUPS[index] for index in mapping], {
        "training_count": len(train),
        "holdout_count": len(holdout),
        "matching_profiles": int(np.count_nonzero(mapping[holdout_groups] == expected)),
    }


@lru_cache(maxsize=1)
def train_latent_clusters() -> tuple[Callable[[np.ndarray], np.ndarray], np.ndarray, np.ndarray, list[str], dict[str, int]]:
    train, origins = synthetic_profiles(29, 80)
    holdout, expected = synthetic_profiles(31, 30)
    rng = np.random.default_rng(41)
    sizes = (3, 8, 2, 8, 3)
    weights = [rng.normal(0, 0.35, (left, right)) for left, right in pairwise(sizes)]
    biases = [np.zeros(size) for size in sizes[1:]]
    center = train.mean(axis=0)

    def encode(values: np.ndarray) -> np.ndarray:
        hidden = np.tanh((values - center) @ weights[0] + biases[0])
        return np.tanh(hidden @ weights[1] + biases[1])

    features = train - center
    for _ in range(1200):
        states = [features]
        for index, (weight, bias) in enumerate(zip(weights, biases, strict=True)):
            values = states[-1] @ weight + bias
            states.append(np.tanh(values) if index < 3 else values)
        delta = (states[-1] - features) / len(features)
        for index in reversed(range(len(weights))):
            previous = (delta @ weights[index].T) * (1 - states[index] ** 2) if index else None
            weights[index] -= 0.15 * (states[index].T @ delta)
            biases[index] -= 0.15 * delta.sum(axis=0)
            if previous is not None:
                delta = previous

    encoded = encode(train)
    centers, assigned = kmeans2(encoded, len(GROUPS), iter=50, minit="++", rng=np.random.default_rng(43), missing="raise")
    mapping = np.asarray([
        np.bincount(origins[assigned == index], minlength=len(GROUPS)).argmax()
        for index in range(len(centers))
    ])
    profiles = np.asarray([train[assigned == index].mean(axis=0) for index in range(len(centers))])
    held_groups = ((encode(holdout)[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return encode, centers, profiles, [GROUPS[index] for index in mapping], {
        "training_count": len(train), "holdout_count": len(holdout),
        "matching_profiles": int(np.count_nonzero(mapping[held_groups] == expected)),
    }


def cluster_student_demo(snapshot: dict[str, Any], model_version: str = STUDENT_MODEL_VERSIONS[0]) -> dict[str, Any]:
    values = {row["name"]: row["normalized"] for row in snapshot.get("ahp", {}).get("dimensions", [])}
    inputs = {name: values.get(name) for name in DIMENSIONS}
    missing = [name for name, value in inputs.items() if value is None]
    projection = None
    if model_version == STUDENT_MODEL_VERSIONS[1]:
        projection, centers, profiles, names, validation = train_latent_clusters()
    else:
        centers, names, validation = train_student_clusters()
        profiles = centers
    selected = None
    if not missing and snapshot["total"] is not None and not snapshot["stale"] and snapshot["rule_currently_enabled"]:
        vector = np.asarray(list(inputs.values()), dtype=float)
        distances = np.linalg.norm(centers - (projection(vector) if projection else vector), axis=1)
        index = int(distances.argmin())
        selected = {
            "name": names[index],
            "distance": round(float(distances[index]), 3),
            "center": dict(zip(DIMENSIONS, (round(float(value), 3) for value in profiles[index]), strict=True)),
        }
    return {"model_version": model_version, "inputs": inputs, "missing": missing,
            "recipe": {"algorithm": "Autoencoder + K-means" if projection else "K-means",
                       "training_seed": 29, "holdout_seed": 31, "distance_space": "latent" if projection else "input"},
            "cluster": selected, "validation": validation}
