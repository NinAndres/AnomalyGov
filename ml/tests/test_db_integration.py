"""Checks against the local database with the full 2025 base. Skipped when DATABASE_URL is not set."""

import os

import numpy as np
import pytest

from anomalygov_ml.sampling import stratified_sample
from anomalygov_ml.sources.payments import FEATURE_COLUMNS, PaymentsAdapter

psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="DATABASE_URL not set")


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        yield connection


def test_features_for_a_small_sample(conn):
    adapter = PaymentsAdapter()
    population = adapter.load_population(conn)
    sample = stratified_sample(population, list(adapter.strata_columns), total=500, floor=5, seed=0)
    features = adapter.load_features(conn, sample["id"].tolist())

    assert list(features.index) == sample["id"].tolist()
    assert list(features.columns) == list(FEATURE_COLUMNS)
    assert np.isfinite(features.to_numpy()).all()
    assert features["favored_months"].between(1, 12).all()
    assert (features["log_amount"] > 0).all()  # zero and negative amounts are excluded at ingestion
