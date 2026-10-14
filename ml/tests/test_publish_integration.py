"""Publishes a real experiment into a throwaway database that stands in for Supabase.

Skipped when DATABASE_URL is not set or the local database has no experiment yet.
"""

import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from anomalygov_ml.publish import publish  # noqa: E402

pytestmark = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="DATABASE_URL not set")

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
TARGET_DB = "anomalygov_publish_test"


@pytest.fixture
def source():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        yield conn


@pytest.fixture
def target(source):
    source.execute(f"DROP DATABASE IF EXISTS {TARGET_DB}")
    source.execute(f"CREATE DATABASE {TARGET_DB}")
    try:
        with psycopg.connect(make_conninfo(os.environ["DATABASE_URL"], dbname=TARGET_DB), autocommit=True) as conn:
            for migration in sorted(MIGRATIONS.glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"))
            yield conn
    finally:
        source.execute(f"DROP DATABASE IF EXISTS {TARGET_DB}")


def test_publish_is_complete_minimal_and_idempotent(source, target):
    row = source.execute(
        "SELECT experiment FROM runs WHERE purpose = 'main' GROUP BY experiment ORDER BY min(id) LIMIT 1"
    ).fetchone()
    if row is None:
        pytest.skip("no experiment in the local database")
    experiment = row[0]

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

    # New rows created on the target (e.g. exploration runs) must not collide with published ids.
    next_id = target.execute(
        """INSERT INTO runs (experiment, config_sha256, mode, purpose, algorithm, params, feature_columns,
                             train_sample_id, n_train, n_scored, fit_seconds, score_seconds, environment)
           VALUES ('x', repeat('0', 64), 'exploration', 'main', 'lof', '{}', '{}', %s, 1, 1, 0, 0, '{}')
           RETURNING id""",
        (main_sample,),
    ).fetchone()[0]
    assert next_id > source.execute("SELECT max(id) FROM runs").fetchone()[0]
