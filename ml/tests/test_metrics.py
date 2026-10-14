import numpy as np
import pytest

from anomalygov_ml.metrics import flagged, jaccard, normalize, spearman


def test_normalize_is_percentile_rank_with_average_ties():
    np.testing.assert_allclose(normalize(np.array([10.0, 30.0, 20.0, 20.0])), [0.25, 1.0, 0.625, 0.625])


def test_flagged_takes_top_share():
    scores = np.arange(100, dtype=float)
    assert flagged(scores, 0.05).sum() == 5
    assert flagged(scores, 0.05)[-5:].all()


def test_flagged_includes_every_tie_at_threshold():
    scores = np.array([0.0] * 90 + [1.0] * 10)
    assert flagged(scores, 0.05).sum() == 10


def test_jaccard():
    a = np.array([True, True, False, False])
    b = np.array([True, False, True, False])
    assert jaccard(a, b) == pytest.approx(1 / 3)
    assert jaccard(np.zeros(3, bool), np.zeros(3, bool)) == 1.0


def test_spearman():
    assert spearman(np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 30.0])) == pytest.approx(1.0)
    assert spearman(np.array([1.0, 2.0, 3.0]), np.array([3.0, 2.0, 1.0])) == pytest.approx(-1.0)
