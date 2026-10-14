"""Score normalization and agreement metrics (decision 0006). No predictive metrics: there are no labels."""

import numpy as np
from scipy.stats import rankdata, spearmanr


def normalize(scores: np.ndarray) -> np.ndarray:
    """Percentile rank in (0, 1]; ties share their average rank."""
    return rankdata(scores, method="average") / len(scores)


def flagged(scores: np.ndarray, p: float) -> np.ndarray:
    """Rows among the top p of the scores. Every row tied at the threshold is flagged."""
    return scores >= np.quantile(scores, 1 - p)


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 1.0


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    return float(spearmanr(a, b).statistic)
