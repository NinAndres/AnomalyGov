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


class FakePortal:
    """Stands in for PortalClient: serves the given items in pages of 15, for any month."""

    def __init__(self, items, error=None):
        self.items, self.error, self.requests = items, error, 0

    def pages(self, endpoint, params):
        if self.error:
            raise self.error
        for start in range(0, len(self.items), 15):
            self.requests += 1
            yield self.items[start:start + 15]


def test_worker_processes_portal_jobs(source, target, experiment):
    from test_portal import sample_item

    from anomalygov_ml.portal.client import PortalError
    from anomalygov_ml.portal.register import agency_options, register

    config = CONFIGS / f"{experiment}.toml"
    if not config.exists():
        pytest.skip(f"no config for {experiment}")
    publish(source, target, experiment)
    register(target, agency_options(source), "2026-10")
    portal = FakePortal([sample_item("portal_contracts", i) for i in range(300)])
    worker = Worker(target, config, Settings(min_rows=100, portal_max_rows=250), portal_client=lambda: portal)

    def create(filters):
        return str(target.execute(
            "INSERT INTO jobs (source, filters, params) VALUES ('portal_contracts', %s, '{\"p\": 0.02}') RETURNING id",
            (Jsonb(filters),),
        ).fetchone()[0])

    ok = create({"agency_code": ["26000"], "period": {"from": "2025-03", "to": "2025-03"}})
    assert worker.run_once()
    status, result, error = job(target, ok)
    assert (status, error) == ("succeeded", None)
    # Truncated at the cap, which the user is told about.
    assert result["portal"]["truncated"] and result["portal"]["received"] == 250 and result["n_used"] == 250
    assert target.execute("SELECT progress->>'phase' FROM jobs WHERE id = %s", (ok,)).fetchone()[0] == "scoring"
    runs = target.execute(
        """SELECT r.algorithm, r.train_sample_id, count(s.*), max(s.normalized_score) FROM runs r
           JOIN portal_scores s ON s.run_id = r.id WHERE r.job_id = %s GROUP BY 1, 2""", (ok,)).fetchall()
    assert sorted(r[0] for r in runs) == ["isolation_forest", "lof", "one_class_svm"]
    assert all(r[1] is None and r[2] == 250 and r[3] == 1.0 for r in runs)
    stored = target.execute("SELECT \"values\" FROM portal_records WHERE job_id = %s", (ok,)).fetchall()
    assert len(stored) == 250 and all("PESSOA" not in str(v) for (v,) in stored)

    # Errors of the API and too small cuts fail the job with a message, writing nothing.
    worker.portal_client = lambda: FakePortal([], PortalError("A API do Portal recusou a chave de acesso do worker."))
    refused = create({"agency_code": ["26000"], "period": {"from": "2025-03", "to": "2025-03"}})
    assert worker.run_once()
    worker.portal_client = lambda: FakePortal([sample_item("portal_contracts", i) for i in range(20)])
    small = create({"agency_code": ["26000"], "period": {"from": "2025-03", "to": "2025-03"}})
    missing = create({"period": {"from": "2025-03", "to": "2025-03"}})
    assert worker.run_once() and worker.run_once()
    assert job(target, refused)[0] == "failed" and "chave" in job(target, refused)[2]
    assert job(target, small)[0] == "failed" and "mínimo" in job(target, small)[2]
    assert job(target, missing)[0] == "failed" and "órgão" in job(target, missing)[2]
    assert target.execute("SELECT count(*) FROM runs WHERE job_id IN (%s, %s, %s)",
                          (refused, small, missing)).fetchone()[0] == 0

    # Deleting the job (retention) deletes its records and scores.
    target.execute("DELETE FROM jobs WHERE id = %s", (ok,))
    assert target.execute("SELECT count(*) FROM portal_records").fetchone()[0] == 0
    assert target.execute("SELECT count(*) FROM portal_scores").fetchone()[0] == 0
