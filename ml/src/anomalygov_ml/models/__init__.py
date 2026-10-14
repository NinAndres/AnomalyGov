"""Anomaly detection algorithms, agnostic to the data source (decision 0006).

Every detector receives only a numeric feature matrix and returns scores where
higher means more anomalous.
"""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM

# Algorithms run single-threaded so that their execution times are comparable.
N_JOBS = 1


def max_duplicate_group(X: np.ndarray, decimals: int = 9) -> int:
    """Size of the largest group of (numerically) identical rows."""
    _, counts = np.unique(np.round(X, decimals), axis=0, return_counts=True)
    return int(counts.max())


class Detector(ABC):
    name: str

    def __init__(self, params: dict[str, Any], random_state: int | None = None):
        self.params = dict(params)
        self.random_state = random_state
        self.resolved_params: dict[str, Any] = {}

    @abstractmethod
    def fit(self, X: np.ndarray) -> None: ...

    @abstractmethod
    def score(self, X: np.ndarray) -> np.ndarray:
        """Anomaly score per row of X (higher = more anomalous)."""


class IsolationForestDetector(Detector):
    name = "isolation_forest"

    def fit(self, X):
        self.model = IsolationForest(**self.params, random_state=self.random_state, n_jobs=N_JOBS).fit(X)
        self.resolved_params = {**self.model.get_params(), "max_samples_effective": int(self.model.max_samples_)}

    def score(self, X):
        return -self.model.score_samples(X)


class OneClassSVMDetector(Detector):
    name = "one_class_svm"

    def fit(self, X):
        self.model = OneClassSVM(**self.params).fit(X)
        self.resolved_params = {
            **self.model.get_params(),
            "gamma_effective": float(self.model._gamma),
            "support_vectors": int(len(self.model.support_)),
        }

    def score(self, X):
        return -self.model.score_samples(X)


class LOFDetector(Detector):
    """Local Outlier Factor.

    `n_neighbors` is either fixed or derived as the largest group of identical rows plus
    `neighbors_margin`, because LOF breaks down when a point has more duplicates than neighbours.
    With `novelty=False` the detector scores its own training matrix only.
    """

    name = "lof"

    def fit(self, X):
        params = dict(self.params)
        largest = max_duplicate_group(X)
        margin = params.pop("neighbors_margin", None)
        if margin is not None:
            params["n_neighbors"] = largest + margin
        self.model = LocalOutlierFactor(**params, n_jobs=N_JOBS).fit(X)
        self._train = X
        self.resolved_params = {**self.model.get_params(), "neighbors_margin": margin, "max_duplicate_group": largest}

    def score(self, X):
        if self.model.novelty:
            return -self.model.score_samples(X)
        if X is not self._train:
            raise ValueError("LOF with novelty=False can only score its own training matrix")
        return -self.model.negative_outlier_factor_


DETECTORS: dict[str, type[Detector]] = {
    cls.name: cls for cls in (IsolationForestDetector, LOFDetector, OneClassSVMDetector)
}
