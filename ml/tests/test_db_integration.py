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

    # The same connection must support repeated calls (one per sample in an experiment).
    again = adapter.load_features(conn, sample["id"].tolist()[:50])
    assert again.equals(features.iloc[:50])


TINY_CONFIG = """
name = "teste-integracao"
source = "payments"
p = [0.01, 0.05]

[sample]
total = 300
floor = 2
seed = 7

[main.isolation_forest]
n_estimators = 10
max_samples = 64
random_state = 0

[main.lof]
neighbors_margin = 5

[main.one_class_svm]
nu = 0.05
gamma = "scale"

[parameter.isolation_forest]
n_estimators = [5, 10]

[artifact.lof]
n_neighbors = [3]

[data_stability]
seeds = [8]

[scalability]
sizes = [200, 400]
repetitions = 1
lof_max_size = 300
"""


def test_tiny_experiment_end_to_end(tmp_path):
    from anomalygov_ml.experiment import PARTS, Experiment

    config = tmp_path / "tiny.toml"
    config.write_text(TINY_CONFIG, encoding="utf-8")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.transaction(force_rollback=True):
        Experiment(conn, config).run(PARTS)
        runs = dict(conn.execute(
            "SELECT purpose, count(*) FROM runs WHERE experiment = 'teste-integracao' GROUP BY purpose"
        ).fetchall())
        # parameter: n_estimators=5 only (10 is the main one); scalability: LOF skipped above 300 rows.
        assert runs == {"main": 3, "parameter": 1, "artifact": 1, "data_stability": 3, "scalability": 5}

        main_scores = conn.execute(
            """SELECT r.algorithm, count(s.*), min(s.normalized_score), max(s.normalized_score),
                      count(*) FILTER (WHERE sr.payment_id IS NULL)
               FROM runs r JOIN run_scores s ON s.run_id = r.id
               LEFT JOIN sample_records sr ON sr.sample_id = r.scored_sample_id AND sr.payment_id = s.payment_id
               WHERE r.experiment = 'teste-integracao' AND r.purpose = 'main' GROUP BY r.algorithm"""
        ).fetchall()
        sample_size = conn.execute(
            "SELECT sample_size FROM samples s JOIN runs r ON r.train_sample_id = s.id "
            "WHERE r.experiment = 'teste-integracao' AND r.purpose = 'main' LIMIT 1"
        ).fetchone()[0]
        for algorithm, n, low, high, outside_sample in main_scores:
            assert n == sample_size, algorithm
            assert 0 < low and high == 1.0
            assert outside_sample == 0

        stability = conn.execute(
            """SELECT bool_and(train_sample_id <> scored_sample_id),
                      bool_and(params->>'novelty' = 'true') FILTER (WHERE algorithm = 'lof')
               FROM runs WHERE experiment = 'teste-integracao' AND purpose = 'data_stability'"""
        ).fetchone()
        assert stability == (True, True)
        assert conn.execute(
            "SELECT count(*) FROM run_scores s JOIN runs r ON r.id = s.run_id "
            "WHERE r.experiment = 'teste-integracao' AND r.purpose = 'scalability'"
        ).fetchone()[0] == 0

        from anomalygov_ml import report

        data = report.load(conn, "teste-integracao")
        run_metrics, run_comparisons = report.compute_tables(data)
        report.store_tables(conn, run_metrics, run_comparisons)
        report.store_tables(conn, run_metrics, run_comparisons)  # idempotent
        # 8 runs scored the main sample (3 main, 1 parameter, 1 artifact, 3 data stability), 3 values of p.
        assert conn.execute(
            "SELECT count(*) FROM run_metrics m JOIN runs r ON r.id = m.run_id WHERE r.experiment = 'teste-integracao'"
        ).fetchone()[0] == 8 * 3
        # 3 pairs among main runs + 5 non-main runs compared with their main run.
        assert len(run_comparisons) == (3 + 5) * 3
        text = report.render(data, run_metrics, run_comparisons)
        for heading in ("Tempo de execução", "Proporção", "Concordância", "Estabilidade", "Características",
                        "Interpretabilidade", "artefato do LOF"):
            assert heading in text


HYPOTHESES_CONFIG = """
base_config = "small.toml"
alpha = 0.05
p = 0.02
p_secondary = 0.05
seed = 0
bootstrap = 500
permutations = 500

[h1]
types = ["individual", "company"]
subsample_fraction = 0.8
subsample_repetitions = 2
manipulation_type = "company"
manipulation_fractions = [0.0, 0.1, 0.3, 0.5]

[h2]
noise_seed = 1
"""


def test_hypotheses_end_to_end(tmp_path):
    from anomalygov_ml import hypotheses
    from anomalygov_ml.experiment import Experiment

    small = TINY_CONFIG.replace('name = "teste-integracao"', 'name = "teste-hipoteses"').replace(
        "total = 300\nfloor = 2", "total = 3000\nfloor = 20")
    (tmp_path / "small.toml").write_text(small, encoding="utf-8")
    config = tmp_path / "hyp.toml"
    config.write_text(HYPOTHESES_CONFIG, encoding="utf-8")

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.transaction(force_rollback=True):
        Experiment(conn, tmp_path / "small.toml").run(("main",))
        for _ in range(2):  # the second run must replace the first one
            hypotheses.run(conn, config)

        runs = dict(conn.execute(
            "SELECT purpose, count(*) FROM runs WHERE experiment = 'teste-hipoteses' AND purpose LIKE 'h%' GROUP BY 1"
        ).fetchall())
        assert runs == {"h2_month": 36, "h2_noise": 12, "h1_cell": 72, "h1_subsample": 24 * 3 * 2,
                        "h1_manipulation": 12 * 4 * 3}
        assert conn.execute(
            "SELECT bool_and(subset IS NOT NULL AND scored_sample_id IS NULL) FROM runs "
            "WHERE experiment = 'teste-hipoteses' AND purpose LIKE 'h%'"
        ).fetchone()[0]

        units = dict(conn.execute(
            "SELECT hypothesis, count(*) FROM hypothesis_units WHERE experiment = 'teste-hipoteses' GROUP BY 1"
        ).fetchall())
        assert units == {"H2": 132 + 12, "H1": 24 + 12 * 4}

        families = dict(conn.execute(
            "SELECT family, count(*) FROM hypothesis_tests WHERE experiment = 'teste-hipoteses' GROUP BY 1"
        ).fetchall())
        assert families == {"H2": 3, "H2_context": 3, "H1a_type": 6, "H1b_association": 18, "H1c_manipulation": 6}
        assert conn.execute(
            """SELECT bool_and(p_adjusted >= p_value AND p_adjusted <= 1 AND p_value BETWEEN 0 AND 1)
               FROM hypothesis_tests WHERE experiment = 'teste-hipoteses'"""
        ).fetchone()[0]
        # Missing values (no confidence interval) must be NULL, never NaN, so the API can serialize them.
        assert conn.execute(
            """SELECT count(*) FROM hypothesis_tests WHERE experiment = 'teste-hipoteses'
               AND 'NaN'::float8 IN (statistic, effect, ci_low, ci_high, p_value, p_adjusted)"""
        ).fetchone()[0] == 0
        from anomalygov_ml import report

        text = report.render_hypotheses(report.load(conn, "teste-hipoteses").hypothesis_tests)
        for family in ("H2:", "H1a:", "H1b:", "H1c:"):
            assert family in text
        # Without manipulation the flags are unchanged: retention is 1 at fraction 0.
        assert conn.execute(
            """SELECT bool_and((measures->>'retention_if')::float = 1) FROM hypothesis_units
               WHERE experiment = 'teste-hipoteses' AND (unit->>'duplicate_fraction')::float = 0"""
        ).fetchone()[0]
