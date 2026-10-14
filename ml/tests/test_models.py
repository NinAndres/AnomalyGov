import numpy as np
import pytest

from anomalygov_ml.models import DETECTORS, LOFDetector, max_duplicate_group

SMALL_PARAMS = {
    "isolation_forest": ({"n_estimators": 50}, 0),
    "lof": ({"n_neighbors": 20}, None),
    "one_class_svm": ({"nu": 0.05, "gamma": "scale"}, None),
}


@pytest.fixture
def data():
    rng = np.random.default_rng(0)
    normal = rng.normal(size=(500, 3))
    # Isolated outliers in different directions. A tight cluster of outliers would be masked by
    # One-Class SVM, which turns such a cluster into support vectors and treats it as normal.
    outliers = np.array([[8, 0, 0], [0, 8, 0], [0, 0, 8], [-8, 0, 0], [0, -8, 0]], dtype=float)
    return np.vstack([normal, outliers])


@pytest.mark.parametrize("name", sorted(DETECTORS))
def test_outliers_get_the_highest_scores(name, data):
    params, random_state = SMALL_PARAMS[name]
    detector = DETECTORS[name](params, random_state)
    detector.fit(data)
    scores = detector.score(data)
    assert scores.shape == (len(data),)
    assert np.isfinite(scores).all()
    # The five planted outliers are the last rows: they must be among the 5% most anomalous.
    top = set(np.argsort(scores)[-25:])
    assert set(range(500, 505)) <= top


def test_isolation_forest_is_reproducible_with_seed(data):
    a = DETECTORS["isolation_forest"]({"n_estimators": 20}, 7)
    b = DETECTORS["isolation_forest"]({"n_estimators": 20}, 7)
    a.fit(data)
    b.fit(data)
    np.testing.assert_array_equal(a.score(data), b.score(data))


def test_max_duplicate_group():
    X = np.array([[1.0, 2.0], [1.0, 2.0], [1.0, 2.0 + 1e-12], [3.0, 4.0]])
    assert max_duplicate_group(X) == 3  # differences below 1e-9 count as identical


def test_lof_neighbors_follow_largest_duplicate_group(data):
    X = np.vstack([data, np.zeros((40, 3))])
    detector = LOFDetector({"neighbors_margin": 10})
    detector.fit(X)
    assert detector.resolved_params["max_duplicate_group"] == 40
    assert detector.resolved_params["n_neighbors"] == 50
    assert np.isfinite(detector.score(X)).all() and detector.score(X).max() < 1e3


def test_lof_without_novelty_only_scores_its_training_matrix(data):
    detector = LOFDetector({"n_neighbors": 10})
    detector.fit(data)
    with pytest.raises(ValueError):
        detector.score(data.copy())


def test_lof_novelty_scores_new_rows(data):
    detector = LOFDetector({"n_neighbors": 10, "novelty": True})
    detector.fit(data[:500])
    scores = detector.score(data)
    assert scores[500:].min() > np.quantile(scores[:500], 0.99)
