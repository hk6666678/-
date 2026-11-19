"""CPU-only clustering exercise using synthetic dimension scores."""

from functools import lru_cache
from itertools import pairwise
from typing import Any

import numpy as np
from scipy.cluster.vq import kmeans2  # type: ignore[import-untyped]

DIMENSIONS = ("学术基础", "科研产出", "学术影响")
GROUPS = ("学术基础较强", "科研产出较强", "多维较均衡")
SYNTHETIC_CENTERS = np.asarray(((0.86, 0.38, 0.44), (0.47, 0.88, 0.49), (0.71, 0.71, 0.76)))
STUDENT_MODEL_VERSIONS = (
    "synthetic-kmeans-v1", "synthetic-autoencoder-v2",
    "synthetic-deep-one-class-v1", "synthetic-deep-two-class-v1",
)


def encode_profile(values: np.ndarray, encoder: dict[str, Any]) -> np.ndarray:
    hidden = np.tanh((values - np.asarray(encoder["center"])) @ np.asarray(encoder["weights"][0]) + np.asarray(encoder["biases"][0]))
    return np.tanh(hidden @ np.asarray(encoder["weights"][1]) + np.asarray(encoder["biases"][1]))


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


def train_encoder(train: np.ndarray) -> dict[str, Any]:
    rng = np.random.default_rng(41)
    sizes = (3, 8, 2, 8, 3)
    weights = [rng.normal(0, 0.35, (left, right)) for left, right in pairwise(sizes)]
    biases = [np.zeros(size) for size in sizes[1:]]
    center = train.mean(axis=0)

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

    return {"center": center.tolist(), "weights": [layer.tolist() for layer in weights[:2]],
            "biases": [layer.tolist() for layer in biases[:2]]}


@lru_cache(maxsize=1)
def train_latent_clusters() -> tuple[dict[str, Any], np.ndarray, np.ndarray, list[str], dict[str, int]]:
    train, origins = synthetic_profiles(29, 80)
    holdout, expected = synthetic_profiles(31, 30)
    encoder = train_encoder(train)
    encoded = encode_profile(train, encoder)
    centers, assigned = kmeans2(encoded, len(GROUPS), iter=50, minit="++", rng=np.random.default_rng(43), missing="raise")
    mapping = np.asarray([
        np.bincount(origins[assigned == index], minlength=len(GROUPS)).argmax()
        for index in range(len(centers))
    ])
    profiles = np.asarray([train[assigned == index].mean(axis=0) for index in range(len(centers))])
    held_groups = ((encode_profile(holdout, encoder)[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return encoder, centers, profiles, [GROUPS[index] for index in mapping], {
        "training_count": len(train), "holdout_count": len(holdout),
        "matching_profiles": int(np.count_nonzero(mapping[held_groups] == expected)),
    }


def class_distances(encoded: np.ndarray, centers: np.ndarray) -> np.ndarray:
    return np.asarray(np.linalg.norm(encoded[..., None, :] - centers, axis=-1))


@lru_cache(maxsize=2)
def reference_class_artifact(model_version: str) -> dict[str, Any]:
    one_class = model_version == "synthetic-deep-one-class-v1"
    train, origins = synthetic_profiles(29, 80)
    holdout, held_origins = synthetic_profiles(31, 30)
    # Profile index 2 is the reference class in this synthetic experiment.
    reference = origins == 2
    expected = held_origins == 2
    encoder = train_encoder(train[reference] if one_class else train)
    encoded = encode_profile(train, encoder)
    profiles = [train[reference].mean(axis=0)]
    centers = [encoded[reference].mean(axis=0)]
    threshold = None
    calibration_count = 0
    if one_class:
        calibration, origin = synthetic_profiles(47, 30)
        reference_calibration = encode_profile(calibration[origin == 2], encoder)
        threshold = float(np.quantile(class_distances(reference_calibration, np.asarray(centers))[:, 0], 0.95))
        calibration_count = len(reference_calibration)
    else:
        centers.append(encoded[~reference].mean(axis=0))
        profiles.append(train[~reference].mean(axis=0))
    distances = class_distances(encode_profile(holdout, encoder), np.asarray(centers))
    predicted = distances[:, 0] <= threshold if threshold is not None else distances.argmin(axis=1) == 0
    return {
        "centers": np.asarray(centers).tolist(), "profiles": np.asarray(profiles).tolist(),
        "names": ["合成参考类", "合成对照类"], "encoder": encoder, "threshold": threshold,
        "validation": {
            "training_count": int(reference.sum()) if one_class else len(train),
            "calibration_count": calibration_count, "holdout_count": len(holdout),
            "matching_profiles": int(np.count_nonzero(predicted == expected)),
            "false_positive": int(np.count_nonzero(predicted & ~expected)),
            "false_negative": int(np.count_nonzero(~predicted & expected)),
        },
        "recipe": {"algorithm": "One-class 自编码器距离识别" if one_class else "Two-class 自编码器最近类中心",
                   "training_seed": 29, "holdout_seed": 31, "distance_space": "latent",
                   "mode": "one_class" if one_class else "two_class", "calibration_seed": 47 if one_class else None},
    }


def cluster_artifact(model_version: str) -> dict[str, Any]:
    if model_version in STUDENT_MODEL_VERSIONS[2:]:
        return reference_class_artifact(model_version)
    encoder = None
    if model_version == STUDENT_MODEL_VERSIONS[1]:
        encoder, centers, profiles, names, validation = train_latent_clusters()
    else:
        centers, names, validation = train_student_clusters()
        profiles = centers
    return {"centers": centers.tolist(), "profiles": profiles.tolist(), "names": names,
            "encoder": encoder, "validation": validation,
            "recipe": {"algorithm": "Autoencoder + K-means" if encoder else "K-means",
                       "training_seed": 29, "holdout_seed": 31, "distance_space": "latent" if encoder else "input"}}


def cluster_student_demo(
    snapshot: dict[str, Any], model_version: str = STUDENT_MODEL_VERSIONS[0],
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if artifact is None:
        artifact = cluster_artifact(model_version)
    values = {row["name"]: row["normalized"] for row in snapshot.get("ahp", {}).get("dimensions", [])}
    inputs = {name: values.get(name) for name in DIMENSIONS}
    missing = [name for name, value in inputs.items() if value is None]
    selected = None
    if not missing and snapshot["total"] is not None and not snapshot["stale"] and snapshot["rule_currently_enabled"]:
        vector = np.asarray(list(inputs.values()), dtype=float)
        encoder = artifact["encoder"]
        projected = encode_profile(vector, encoder) if encoder else vector
        distances = class_distances(projected, np.asarray(artifact["centers"]))
        index = int(distances.argmin())
        threshold = artifact.get("threshold")
        selected = {
            "name": "偏离合成参考类" if threshold is not None and distances[index] > threshold else artifact["names"][index],
            "distance": round(float(distances[index]), 3),
            "threshold": round(threshold, 3) if threshold is not None else None,
            "center": dict(zip(DIMENSIONS, (round(float(value), 3) for value in artifact["profiles"][index]), strict=True)),
        }
    return {"model_version": model_version, "inputs": inputs, "missing": missing,
            "recipe": artifact["recipe"], "cluster": selected, "validation": artifact["validation"]}
