import math

import numpy as np
import pandas as pd
import pytest

from anomalygov_ml.sources.payments import FEATURE_COLUMNS, MAD_OFFSET, compute_features


@pytest.fixture
def history():
    # Favored 1: three months, two UGs. Favored 2: a single record.
    return pd.DataFrame(
        {
            "id": [10, 11, 12, 20],
            "favored_id": [1, 1, 1, 2],
            "reference_month": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01", "2025-01-01"]),
            "management_unit_code": ["A", "A", "B", "A"],
            "amount": [100.0, 100.0, 1000.0, 50.0],
        }
    )


@pytest.fixture
def ug_log_median():
    return pd.Series({"A": math.log1p(100), "B": math.log1p(500)})


def test_columns_and_index(history, ug_log_median):
    features = compute_features(history, ug_log_median)
    assert list(features.columns) == list(FEATURE_COLUMNS)
    assert list(features.index) == [10, 11, 12, 20]
    assert np.isfinite(features.to_numpy()).all()


def test_log_amount_and_amount_vs_ug(history, ug_log_median):
    features = compute_features(history, ug_log_median)
    assert features.loc[12, "log_amount"] == pytest.approx(math.log1p(1000))
    assert features.loc[10, "amount_vs_ug"] == pytest.approx(0)
    assert features.loc[12, "amount_vs_ug"] == pytest.approx(math.log1p(1000) - math.log1p(500))


def test_amount_vs_favored_is_robust_z_score(history, ug_log_median):
    features = compute_features(history, ug_log_median)
    # Favored 1 logs: [l100, l100, l1000] -> median l100, MAD 0.
    assert features.loc[10, "amount_vs_favored"] == pytest.approx(0)
    assert features.loc[12, "amount_vs_favored"] == pytest.approx((math.log1p(1000) - math.log1p(100)) / MAD_OFFSET)
    # A favored with a single record is never atypical for itself.
    assert features.loc[20, "amount_vs_favored"] == pytest.approx(0)


def test_favored_recurrence_and_reach(history, ug_log_median):
    features = compute_features(history, ug_log_median)
    assert features.loc[10, "favored_months"] == 3
    assert features.loc[20, "favored_months"] == 1
    assert features.loc[10, "favored_ug_count"] == pytest.approx(math.log1p(2))
    assert features.loc[20, "favored_ug_count"] == pytest.approx(math.log1p(1))


def test_does_not_modify_input(history, ug_log_median):
    before = history.copy()
    compute_features(history, ug_log_median)
    pd.testing.assert_frame_equal(history, before)
