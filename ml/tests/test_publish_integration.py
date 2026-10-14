"""Publishes a real experiment into a throwaway database that stands in for Supabase.

Skipped when DATABASE_URL is not set or the local database has no experiment yet.
"""

import pytest

pytest.importorskip("psycopg")
from anomalygov_ml.publish import publish  # noqa: E402


def test_publish_is_complete_minimal_and_idempotent(source, target, experiment):
    first = publish(source, target, experiment)
    second = publish(source, target, experiment)

    main_sample, sample_size = source.execute(
        """SELECT s.id, s.sample_size FROM samples s JOIN runs r ON r.scored_sample_id = s.id
           WHERE r.experiment = %s AND r.purpose = 'main' LIMIT 1""",
        (experiment,),
    ).fetchone()
    n_runs = source.execute("SELECT count(*) FROM runs WHERE experiment = %s", (experiment,)).fetchone()[0]

    assert first["payments"] == sample_size
    assert first["runs"] == n_runs
    assert first["run_scores"] == 3 * sample_size  # only the three main runs
    assert first["record_features"] == sample_size
    assert second["payments"] == 0 and second["runs"] == 0 and second["run_scores"] == 0

    counts = target.execute(
        """SELECT (SELECT count(*) FROM payments), (SELECT count(*) FROM sample_records),
                  (SELECT count(*) FROM favored WHERE favored_type = 'individual' AND (code IS NOT NULL OR name IS NOT NULL)),
                  (SELECT count(*) FROM run_metrics), (SELECT count(*) FROM run_comparisons)"""
    ).fetchone()
    source_metrics = source.execute(
        """SELECT (SELECT count(*) FROM run_metrics m JOIN runs r ON r.id = m.run_id WHERE r.experiment = %s),
                  (SELECT count(*) FROM run_comparisons c JOIN runs r ON r.id = c.run_a WHERE r.experiment = %s)""",
        (experiment, experiment),
    ).fetchone()
    assert counts == (sample_size, sample_size, 0, *source_metrics)

    hypothesis_counts = "SELECT (SELECT count(*) FROM hypothesis_units WHERE experiment = %s), "                         "(SELECT count(*) FROM hypothesis_tests WHERE experiment = %s)"
    assert target.execute(hypothesis_counts, (experiment, experiment)).fetchone() ==         source.execute(hypothesis_counts, (experiment, experiment)).fetchone()

    # New rows created on the target (e.g. exploration runs) must not collide with published ids.
    next_id = target.execute(
        """INSERT INTO runs (experiment, config_sha256, mode, purpose, algorithm, params, feature_columns,
                             train_sample_id, n_train, n_scored, fit_seconds, score_seconds, environment)
           VALUES ('x', repeat('0', 64), 'exploration', 'main', 'lof', '{}', '{}', %s, 1, 1, 0, 0, '{}')
           RETURNING id""",
        (main_sample,),
    ).fetchone()[0]
    assert next_id > source.execute("SELECT max(id) FROM runs").fetchone()[0]
