"""Fixtures for tests that need the local database (skipped when DATABASE_URL is not set)."""

import os
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
TARGET_DB = "anomalygov_publish_test"


@pytest.fixture
def source():
    """Connection to the local database with the full base and the experiments."""
    psycopg = pytest.importorskip("psycopg")
    if "DATABASE_URL" not in os.environ:
        pytest.skip("DATABASE_URL not set")
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        yield conn


@pytest.fixture
def target(source):
    """Throwaway database with every migration applied, standing in for Supabase."""
    import psycopg
    from psycopg.conninfo import make_conninfo

    source.execute(f"DROP DATABASE IF EXISTS {TARGET_DB}")
    source.execute(f"CREATE DATABASE {TARGET_DB}")
    try:
        with psycopg.connect(make_conninfo(os.environ["DATABASE_URL"], dbname=TARGET_DB), autocommit=True) as conn:
            for migration in sorted(MIGRATIONS.glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"))
            yield conn
    finally:
        source.execute(f"DROP DATABASE IF EXISTS {TARGET_DB}")


@pytest.fixture
def experiment(source):
    """Name of the first experiment with main runs in the local database."""
    row = source.execute(
        "SELECT experiment FROM runs WHERE purpose = 'main' AND mode = 'experiment' GROUP BY experiment ORDER BY min(id) LIMIT 1"
    ).fetchone()
    if row is None:
        pytest.skip("no experiment in the local database")
    return row[0]
