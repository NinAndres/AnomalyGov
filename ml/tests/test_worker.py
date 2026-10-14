import uuid

import pytest

from anomalygov_ml.worker import JobError, Settings, filter_sql, job_seed

DEFINITIONS = [
    {"name": "reference_month", "type": "month_range"},
    {"name": "uf", "type": "select"},
    {"name": "amount", "type": "number_range"},
]


def test_filter_sql_builds_parameterized_clauses():
    where, params = filter_sql(
        {"reference_month": {"from": "2025-02", "to": "2025-04"}, "uf": ["SP", "RJ"], "amount": {"min": 10}},
        DEFINITIONS,
    )
    assert where == ('d."reference_month" >= %s AND d."reference_month" <= %s AND d."uf" = ANY (%s) '
                     'AND d."amount" >= %s')
    assert params == ["2025-02", "2025-04", ["SP", "RJ"], 10]


def test_filter_sql_without_filters_selects_everything():
    assert filter_sql({}, DEFINITIONS) == ("true", [])


def test_filter_sql_rejects_unknown_filters():
    with pytest.raises(JobError):
        filter_sql({"favored_name": ["x"]}, DEFINITIONS)


def test_filter_sql_rejects_unsafe_names_even_if_declared():
    with pytest.raises(JobError):
        filter_sql({'uf"; DROP TABLE jobs; --': ["SP"]}, [{"name": 'uf"; DROP TABLE jobs; --', "type": "select"}])


def test_job_seed_is_deterministic_and_fits_numpy():
    job_id = str(uuid.uuid4())
    assert job_seed(job_id) == job_seed(job_id)
    assert 0 <= job_seed(job_id) < 2**31


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("EXPLORATION_MAX_ROWS", "1234")
    monkeypatch.setenv("EXPLORATION_RETENTION_HOURS", "0.5")
    settings = Settings.from_env()
    assert settings.max_rows == 1234 and settings.retention_hours == 0.5 and settings.min_rows == 100
