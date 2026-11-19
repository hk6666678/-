"""CPU-only clustering exercise using synthetic dimension scores."""

from functools import lru_cache
from typing import Any

import numpy as np
from scipy.cluster.vq import kmeans2  # type: ignore[import-untyped]

DIMENSIONS = ("学术基础", "科研产出", "学术影响")
GROUPS = ("学术基础较强", "科研产出较强", "多维较均衡")
SYNTHETIC_CENTERS = np.asarray(((0.86, 0.38, 0.44), (0.47, 0.88, 0.49), (0.71, 0.71, 0.76)))


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


def cluster_student_demo(snapshot: dict[str, Any]) -> dict[str, Any]:
    values = {row["name"]: row["normalized"] for row in snapshot.get("ahp", {}).get("dimensions", [])}
    inputs = {name: values.get(name) for name in DIMENSIONS}
    missing = [name for name, value in inputs.items() if value is None]
    centers, names, validation = train_student_clusters()
    selected = None
    if not missing and snapshot["total"] is not None and not snapshot["stale"] and snapshot["rule_currently_enabled"]:
        distances = np.linalg.norm(centers - np.asarray(list(inputs.values()), dtype=float), axis=1)
        index = int(distances.argmin())
        selected = {
            "name": names[index],
            "distance": round(float(distances[index]), 3),
            "center": dict(zip(DIMENSIONS, (round(float(value), 3) for value in centers[index]), strict=True)),
        }
    return {"model_version": "synthetic-kmeans-v1", "inputs": inputs, "missing": missing,
            "cluster": selected, "validation": validation}
