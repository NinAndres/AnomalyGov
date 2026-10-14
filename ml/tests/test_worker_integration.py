"""Worker against a throwaway database with a published experiment (skipped without DATABASE_URL)."""

from pathlib import Path

import pytest

pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb  # noqa: E402

from anomalygov_ml.publish import publish  # noqa: E402
from anomalygov_ml.worker import Settings, Worker  # noqa: E402

CONFIGS = Path(__file__).resolve().parents[1] / "experiments" / "configs"


def create_job(conn, filters, params=None) -> str:
    return str(conn.execute(
        "INSERT INTO jobs (source, filters, params) VALUES ('payments', %s, %s) RETURNING id",
        (Jsonb(filters), Jsonb(params or {"p": 0.01})),
    ).fetchone()[0])


def job(conn, job_id):
    return conn.execute("SELECT status, result, error FROM jobs WHERE id = %s", (job_id,)).fetchone()


def test_worker_processes_jobs_end_to_end(source, target, experiment):
    config = CONFIGS / f"{experiment}.toml"
    if not config.exists():
        pytest.skip(f"no config for {experiment}")
    publish(source, target, experiment)
    worker = Worker(target, config, Settings(max_rows=1000, min_rows=100))

    filters = {"favored_type": ["company"], "reference_month": {"from": "2025-01", "to": "2025-02"}}
    small = create_job(target, filters)
    tiny = create_job(target, {"favored_type": ["special"], "uf": ["AC"]})
    everything = create_job(target, {})
    for _ in range(3):
        assert worker.run_once()
    assert not worker.run_once()  # queue empty

    # A filtered job below the row cap uses every matching record.
    expected = target.execute(
        """SELECT count(*) FROM payments_display d WHERE d.favored_type = 'company'
           AND d.reference_month BETWEEN '2025-01' AND '2025-02'"""
    ).fetchone()[0]
    status, result, error = job(target, small)
    assert (status, error) == ("succeeded", None)
    assert result["n_filtered"] == expected and result["n_used"] == min(expected, 1000)
    runs = target.execute(
        """SELECT r.algorithm, r.mode, r.experiment, count(s.*), min(s.normalized_score), max(s.normalized_score)
           FROM runs r JOIN run_scores s ON s.run_id = r.id WHERE r.job_id = %s GROUP BY 1, 2, 3""",
        (small,),
    ).fetchall()
    assert {r[0] for r in runs} == {"isolation_forest", "lof", "one_class_svm"}
    for _, mode, name, n, low, high in runs:
        assert (mode, name, n, high) == ("exploration", "exploration", result["n_used"], 1.0) and low > 0
    assert set(result["runs"].values()) == {r[0] for r in target.execute(
        "SELECT id FROM runs WHERE job_id = %s", (small,)).fetchall()}

    # Too few records: failed with a message for the user, and nothing written.
    status, result, error = job(target, tiny)
    assert status == "failed" and "mínimo" in error and result is None
    assert target.execute("SELECT count(*) FROM runs WHERE job_id = %s", (tiny,)).fetchone()[0] == 0

    # Above the cap: a reproducible sample of max_rows records.
    status, result, _ = job(target, everything)
    assert status == "succeeded" and result["sampled"] and result["n_used"] == 1000
    assert result["n_filtered"] > 1000 and result["sample_seed"] is not None


def test_housekeeping_fails_stale_jobs_and_deletes_old_ones(source, target, experiment):
    config = CONFIGS / f"{experiment}.toml"
    if not config.exists():
        pytest.skip(f"no config for {experiment}")
    publish(source, target, experiment)
    worker = Worker(target, config, Settings(retention_hours=24, stale_minutes=30))
    stale = target.execute(
        """INSERT INTO jobs (source, status, started_at) VALUES ('payments', 'running', now() - interval '2 hours')
           RETURNING id"""
    ).fetchone()[0]
    old = target.execute(
        """INSERT INTO jobs (source, status, result, started_at, finished_at)
           VALUES ('payments', 'succeeded', '{}', now() - interval '3 days', now() - interval '3 days') RETURNING id"""
    ).fetchone()[0]
    recent = target.execute(
        """INSERT INTO jobs (source, status, result, started_at, finished_at)
           VALUES ('payments', 'succeeded', '{}', now(), now()) RETURNING id"""
    ).fetchone()[0]

    assert not worker.run_once()
    assert target.execute("SELECT status, error IS NOT NULL FROM jobs WHERE id = %s", (stale,)).fetchone() == ("failed", True)
    assert target.execute("SELECT count(*) FROM jobs WHERE id = %s", (old,)).fetchone()[0] == 0
    assert target.execute("SELECT count(*) FROM jobs WHERE id = %s", (recent,)).fetchone()[0] == 1
