"""Statistical tests used for hypotheses H1 and H2 (decision 0008)."""

import numpy as np
from scipy.stats import rankdata


def holm(p_values: list[float]) -> list[float]:
    """Holm–Bonferroni adjusted p-values, in the original order."""
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(p) - rank) * p[i])
        adjusted[i] = min(running, 1.0)
    return adjusted.tolist()


def spearman_permutation(x: np.ndarray, y: np.ndarray, permutations: int, seed: int) -> tuple[float, float]:
    """Spearman correlation and its two-sided permutation p-value."""
    rx = rankdata(x)
    ry = rankdata(y)
    rx = (rx - rx.mean()) / rx.std()
    ry = (ry - ry.mean()) / ry.std()
    observed = float(np.mean(rx * ry))
    rng = np.random.default_rng(seed)
    shuffled = np.array([rng.permutation(ry) for _ in range(permutations)])
    null = shuffled @ rx / len(rx)
    p_value = (np.sum(np.abs(null) >= abs(observed) - 1e-12) + 1) / (permutations + 1)
    return observed, float(p_value)


def block_bootstrap_mean(values: np.ndarray, blocks: np.ndarray, resamples: int, seed: int,
                         level: float = 0.95) -> tuple[float, float]:
    """Percentile confidence interval of the mean of `values`, resampling whole blocks with replacement."""
    labels, block_index = np.unique(blocks, return_inverse=True)
    sums = np.bincount(block_index, weights=values)
    counts = np.bincount(block_index)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(labels), size=(resamples, len(labels)))
    means = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    tail = (1 - level) / 2
    return float(np.quantile(means, tail)), float(np.quantile(means, 1 - tail))


def rank_biserial(u_statistic: float, n1: int, n2: int) -> float:
    """Effect size of the Mann–Whitney U of the first group: +1 when every value of group 1 is larger."""
    return 2 * u_statistic / (n1 * n2) - 1
