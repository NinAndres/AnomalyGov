import numpy as np
import pandas as pd
import pytest

from anomalygov_ml.report import dominant_feature, group_profile, num, overlap_counts, surrogate_tree, weighted_share


def test_weighted_share():
    mask = np.array([True, False, False])
    assert weighted_share(mask, np.array([1.0, 1.0, 2.0])) == pytest.approx(0.25)


def test_overlap_counts():
    flags = {
        "a": np.array([True, True, False, False]),
        "b": np.array([True, False, True, False]),
        "c": np.array([True, False, False, False]),
    }
    assert overlap_counts(flags) == {1: 2, 2: 0, 3: 1}


def test_group_profile_uses_weights():
    groups = pd.Series(["x", "x", "y", "y"])
    flags = np.array([True, False, True, False])
    weights = np.array([1.0, 1.0, 3.0, 3.0])
    profile = group_profile(flags, groups, weights)
    assert profile.loc["x", "population_share"] == pytest.approx(0.25)
    assert profile.loc["y", "flagged_share"] == pytest.approx(0.75)
    assert profile.loc["x", "flagged_rate"] == pytest.approx(0.5)


def test_dominant_feature():
    X = np.array([[5.0, 0.1], [0.1, -7.0], [0.2, 0.3]])
    flags = np.array([True, True, False])
    assert dominant_feature(X, flags, ["a", "b"]).to_dict() == {"a": 0.5, "b": 0.5}


def test_surrogate_tree_reproduces_a_step_score():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(1000, 2))
    scores = np.where(X[:, 0] > 2, 1.0, 0.1)
    fidelity, rules = surrogate_tree(X, scores, ["amount", "other"])
    assert fidelity == pytest.approx(1.0)
    assert "amount" in rules and "other" not in rules


def test_surrogate_tree_has_low_fidelity_for_noise():
    rng = np.random.default_rng(0)
    fidelity, _ = surrogate_tree(rng.normal(size=(1000, 2)), rng.random(1000), ["a", "b"])
    assert fidelity < 0.1


def test_num_uses_brazilian_separators():
    assert num(1234567.891, 2) == "1.234.567,89"
    assert num(0.5) == "0,500"
