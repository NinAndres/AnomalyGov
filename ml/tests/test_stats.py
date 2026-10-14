import numpy as np
import pytest
from scipy.stats import mannwhitneyu, spearmanr

from anomalygov_ml.stats import block_bootstrap_mean, holm, rank_biserial, spearman_permutation


def test_holm_matches_hand_computation():
    # Sorted: 0.01*3=0.03, 0.02*2=0.04, 0.04*1=0.04 (monotone).
    assert holm([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])


def test_holm_caps_at_one():
    assert holm([0.6, 0.7]) == pytest.approx([1.0, 1.0])


def test_spearman_permutation_detects_monotone_relation():
    x = np.arange(30, dtype=float)
    rho, p = spearman_permutation(x, x**2, permutations=2000, seed=0)
    assert rho == pytest.approx(spearmanr(x, x**2).statistic)
    assert p < 0.01


def test_spearman_permutation_is_not_significant_for_noise():
    rng = np.random.default_rng(1)
    _, p = spearman_permutation(rng.normal(size=40), rng.normal(size=40), permutations=2000, seed=0)
    assert p > 0.05


def test_block_bootstrap_interval_contains_mean_and_widens_with_block_heterogeneity():
    rng = np.random.default_rng(0)
    blocks = np.repeat(np.arange(12), 11)
    homogeneous = rng.normal(0.1, 0.05, size=len(blocks))
    heterogeneous = homogeneous + np.repeat(rng.normal(0, 0.2, size=12), 11)
    low, high = block_bootstrap_mean(homogeneous, blocks, 2000, seed=0)
    assert low < homogeneous.mean() < high
    low2, high2 = block_bootstrap_mean(heterogeneous, blocks, 2000, seed=0)
    assert (high2 - low2) > 2 * (high - low)


def test_rank_biserial_extremes_and_scipy_convention():
    a, b = np.array([5.0, 6.0, 7.0]), np.array([1.0, 2.0])
    u = mannwhitneyu(a, b).statistic
    assert rank_biserial(u, len(a), len(b)) == pytest.approx(1.0)
    u = mannwhitneyu(b, a).statistic
    assert rank_biserial(u, len(b), len(a)) == pytest.approx(-1.0)
