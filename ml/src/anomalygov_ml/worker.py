"""Worker of the exploration mode: processes the jobs created by the backend (docs/contratos.md, decision 0010).

Usage: python -m anomalygov_ml.worker --config experiments/configs/principal-2025.toml [--once] [--poll SECONDS]

Connects to SUPABASE_DATABASE_URL. Settings (environment): EXPLORATION_MAX_ROWS (50000), EXPLORATION_MIN_ROWS
(100), EXPLORATION_RETENTION_HOURS (24), EXPLORATION_STALE_MINUTES (30), EXPLORATION_PORTAL_MAX_ROWS (10000).
Jobs of Portal API bases (decision 0014) also need PORTAL_API_KEY.
"""

import argparse
import hashlib
import logging
import os
import re
import time
import tomllib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from psycopg.types.json import Jsonb
from sklearn.preprocessing import RobustScaler

from anomalygov_ml import metrics
from anomalygov_ml.experiment import environment, insert_run
from anomalygov_ml.models import DETECTORS
from anomalygov_ml.portal.bases import BASES, compute_features, display_values, fetch, normalize
from anomalygov_ml.portal.client import PortalClient, PortalError

ALGORITHMS = ("isolation_forest", "lof", "one_class_svm")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
EXPERIMENT = "exploration"
RECONNECT_SECONDS = 10
PROGRESS_SECONDS = 3.0  # minimum interval between progress updates written to the job
log = logging.getLogger("anomalygov.worker")


class JobError(Exception):
    """Failure whose message is shown to the user as the job error."""


@dataclass(frozen=True)
class Settings:
    max_rows: int = 50000
    min_rows: int = 100
    retention_hours: float = 24
    stale_minutes: float = 30
    portal_max_rows: int = 10000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            max_rows=int(os.environ.get("EXPLORATION_MAX_ROWS", cls.max_rows)),
            min_rows=int(os.environ.get("EXPLORATION_MIN_ROWS", cls.min_rows)),
            retention_hours=float(os.environ.get("EXPLORATION_RETENTION_HOURS", cls.retention_hours)),
            stale_minutes=float(os.environ.get("EXPLORATION_STALE_MINUTES", cls.stale_minutes)),
            portal_max_rows=int(os.environ.get("EXPLORATION_PORTAL_MAX_ROWS", cls.portal_max_rows)),
        )


def identifier(name: str) -> str:
    if not IDENTIFIER.match(name):
        raise JobError(f"Nome inválido: {name}")
    return name


def filter_sql(filters: dict[str, Any], definitions: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    """WHERE clause over the `<source>_display` view (alias d), whose columns are named after the filters."""
    by_name = {d["name"]: d for d in definitions}
    clauses, params = [], []
    for name, value in filters.items():
        definition = by_name.get(name)
        if definition is None:
            raise JobError(f"Filtro desconhecido: {name}")
        column = f'd."{identifier(name)}"'
        kind = definition["type"]
        if kind == "month_range":
            bounds = (("from", ">="), ("to", "<="))
        elif kind == "number_range":
            bounds = (("min", ">="), ("max", "<="))
        elif kind == "select":
            clauses.append(f"{column} = ANY (%s)")
            params.append(list(value))
            continue
        else:
            raise JobError(f"Tipo de filtro não suportado: {kind}")
        for key, operator in bounds:
            if value.get(key) is not None:
                clauses.append(f"{column} {operator} %s")
                params.append(value[key])
    return " AND ".join(clauses) or "true", params


def job_seed(job_id: str) -> int:
    """Deterministic sampling seed derived from the job id, recorded in the result."""
    return uuid.UUID(str(job_id)).int % (2**31)


def claim(conn: psycopg.Connection) -> dict[str, Any] | None:
    with conn.transaction():
        row = conn.execute(
            """SELECT id, source, filters, params FROM jobs WHERE status = 'pending'
               ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"""
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE jobs SET status = 'running', started_at = now() WHERE id = %s", (row[0],))
    return {"id": str(row[0]), "source": row[1], "filters": row[2], "params": row[3]}


def finish(cur: psycopg.Cursor, job_id: str, result: dict[str, Any]) -> None:
    cur.execute(
        """UPDATE jobs SET status = 'succeeded', finished_at = now(), result = %s
           WHERE id = %s AND status = 'running'""",
        (Jsonb(result), job_id),
    )


def fail(conn: psycopg.Connection, job_id: str, message: str) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'failed', finished_at = now(), error = %s WHERE id = %s AND status = 'running'",
        (message, job_id),
    )


def housekeeping(conn: psycopg.Connection, settings: Settings) -> None:
    """Fail jobs left running by a crashed worker and delete old finished jobs (their runs and scores cascade)."""
    stale = conn.execute(
        """UPDATE jobs SET status = 'failed', finished_at = now(), error = %s
           WHERE status = 'running' AND started_at < now() - make_interval(secs => %s)""",
        ("O processamento foi interrompido. Crie o job novamente.", settings.stale_minutes * 60),
    ).rowcount
    deleted = conn.execute(
        """DELETE FROM jobs WHERE status IN ('succeeded', 'failed')
           AND finished_at < now() - make_interval(secs => %s)""",
        (settings.retention_hours * 3600,),
    ).rowcount
    if stale or deleted:
        log.info("limpeza: %s jobs interrompidos marcados como falhos, %s jobs antigos removidos", stale, deleted)


class Worker:
    def __init__(self, conn: psycopg.Connection, config_path: Path, settings: Settings,
                 portal_client: Callable[[], PortalClient] = PortalClient.from_env):
        raw = config_path.read_bytes()
        config = tomllib.loads(raw.decode("utf-8"))
        self.conn = conn
        self.settings = settings
        self.portal_client = portal_client
        self.main_params: dict[str, dict[str, Any]] = config["main"]
        self.config_sha256 = hashlib.sha256(raw).hexdigest()
        self.environment = environment()
        row = conn.execute(
            """SELECT scored_sample_id FROM runs
               WHERE experiment = %s AND mode = 'experiment' AND purpose = 'main' LIMIT 1""",
            (config["name"],),
        ).fetchone()
        if row is None:
            raise ValueError(f"o experimento {config['name']!r} não está publicado neste banco")
        self.sample_id = row[0]

    def process(self, job: dict[str, Any]) -> dict[str, Any]:
        source = identifier(job["source"])
        definition = self.conn.execute(
            "SELECT filters, feature_columns, kind FROM sources WHERE name = %s", (source,)
        ).fetchone()
        if definition is None:
            raise JobError(f"Base desconhecida: {source}")
        filter_definitions, feature_columns, kind = definition
        if kind == "portal":
            return self.process_portal(job, list(feature_columns))
        where, params = filter_sql(job["filters"], filter_definitions)
        rows = self.conn.execute(
            f"""SELECT d.id, f."values" FROM {source}_display d
                JOIN record_features f ON f.source = %s AND f.record_id = d.id
                WHERE {where} ORDER BY d.id""",
            [source, *params],
        ).fetchall()

        n_filtered = len(rows)
        if n_filtered < self.settings.min_rows:
            raise JobError(f"O recorte tem {n_filtered} registros; o mínimo é {self.settings.min_rows}. "
                           "Amplie os filtros.")
        sampled = n_filtered > self.settings.max_rows
        seed = job_seed(job["id"]) if sampled else None
        if sampled:
            keep = np.sort(np.random.default_rng(seed).choice(n_filtered, self.settings.max_rows, replace=False))
            rows = [rows[i] for i in keep]
        ids = [r[0] for r in rows]
        outputs = self.run_algorithms(RobustScaler().fit_transform(np.array([r[1] for r in rows], dtype=float)))

        subset = {"filters": job["filters"], "sampled": sampled, "sample_seed": seed}
        with self.conn.transaction(), self.conn.cursor() as cur:
            run_ids = self.save_runs(cur, job, outputs, list(feature_columns), ids, subset, self.sample_id,
                                     "COPY run_scores (run_id, payment_id, raw_score, normalized_score) FROM STDIN")
            result = {"n_filtered": n_filtered, "n_used": len(ids), "sampled": sampled, "sample_seed": seed,
                      "runs": run_ids}
            finish(cur, job["id"], result)
        return result

    def process_portal(self, job: dict[str, Any], feature_columns: list[str]) -> dict[str, Any]:
        """Download the cut from the Portal API, then score it like a sample cut (decision 0014)."""
        base = BASES.get(job["source"])
        if base is None:
            raise JobError(f"Base do Portal desconhecida: {job['source']}")
        if list(base.feature_columns) != feature_columns:
            raise JobError("A definição da base está desatualizada. Registre as bases do Portal novamente.")
        agencies = job["filters"].get("agency_code") or []
        period = job["filters"].get("period") or {}
        if len(agencies) != 1 or not period.get("from") or not period.get("to"):
            raise JobError("Informe um órgão e o período (mês inicial e final) para consultar o Portal.")

        last_report = 0.0

        def on_page(month: str, received: int) -> None:
            nonlocal last_report
            if time.monotonic() - last_report >= PROGRESS_SECONDS:
                self.report_progress(job["id"], {"phase": "fetching", "month": month, "received": received,
                                                 "requests": client.requests})
                last_report = time.monotonic()

        try:
            client = self.portal_client()
            fetched = fetch(client, base, agencies[0], period["from"], period["to"], self.settings.portal_max_rows,
                            on_page)
        except PortalError as error:
            raise JobError(str(error)) from None
        self.report_progress(job["id"], {"phase": "scoring", "received": len(fetched.items),
                                         "requests": fetched.requests})

        df, excluded = normalize(base, fetched.items)
        if len(df) < self.settings.min_rows:
            raise JobError(f"O Portal devolveu {len(df)} registros utilizáveis para este órgão e período; o mínimo "
                           f"é {self.settings.min_rows}. Amplie o período ou escolha outro órgão.")
        features = compute_features(base, df)
        outputs = self.run_algorithms(RobustScaler().fit_transform(features.to_numpy()))

        portal = {"requests": fetched.requests, "received": len(fetched.items), "excluded": excluded,
                  "truncated": fetched.truncated, "max_rows": self.settings.portal_max_rows}
        subset = {"filters": job["filters"], "portal": portal}
        with self.conn.transaction(), self.conn.cursor() as cur:
            ids = [row[0] for row in cur.execute(
                "SELECT nextval(pg_get_serial_sequence('portal_records', 'id')) FROM generate_series(1, %s)",
                (len(df),),
            ).fetchall()]
            with cur.copy('COPY portal_records (id, job_id, "values", features) FROM STDIN') as copy:
                copy.set_types(["int8", "uuid", "jsonb", "float8[]"])
                for record_id, values, row in zip(ids, display_values(base, df), features.to_numpy()):
                    copy.write_row((record_id, uuid.UUID(job["id"]), Jsonb(values), [float(v) for v in row]))
            run_ids = self.save_runs(cur, job, outputs, feature_columns, ids, subset, None,
                                     "COPY portal_scores (run_id, record_id, raw_score, normalized_score) FROM STDIN")
            result = {"n_filtered": len(df), "n_used": len(df), "sampled": False, "sample_seed": None,
                      "runs": run_ids, "portal": portal}
            finish(cur, job["id"], result)
        return result

    def run_algorithms(self, X: np.ndarray) -> list[tuple]:
        outputs = []
        for algorithm in ALGORITHMS:
            params = dict(self.main_params[algorithm])
            random_state = params.pop("random_state", None)
            detector = DETECTORS[algorithm](params, random_state)
            start = time.perf_counter()
            detector.fit(X)
            fit_seconds = time.perf_counter() - start
            start = time.perf_counter()
            scores = detector.score(X)
            outputs.append((algorithm, detector, random_state, scores, fit_seconds, time.perf_counter() - start))
        return outputs

    def save_runs(self, cur: psycopg.Cursor, job: dict[str, Any], outputs: list[tuple], feature_columns: list[str],
                  ids: list[int], subset: dict[str, Any], sample_id: int | None, copy_sql: str) -> dict[str, int]:
        """One row in `runs` per algorithm and its scores (copy_sql: COPY into the scores table of the source)."""
        run_ids = {}
        for algorithm, detector, random_state, scores, fit_seconds, score_seconds in outputs:
            run_id = insert_run(
                cur, EXPERIMENT, self.config_sha256, "main", algorithm, detector.resolved_params, random_state,
                feature_columns, sample_id, sample_id, len(ids), len(ids), fit_seconds, score_seconds,
                self.environment, subset, mode="exploration", job_id=job["id"],
            )
            normalized = metrics.normalize(scores)
            with cur.copy(copy_sql) as copy:
                for record_id, raw, norm in zip(ids, scores, normalized):
                    copy.write_row((run_id, record_id, float(raw), float(norm)))
            run_ids[algorithm] = run_id
        return run_ids

    def report_progress(self, job_id: str, progress: dict[str, Any]) -> None:
        self.conn.execute("UPDATE jobs SET progress = %s WHERE id = %s AND status = 'running'",
                          (Jsonb(progress), job_id))

    def run_once(self) -> bool:
        """Process the oldest pending job, if any. Returns whether a job was processed."""
        housekeeping(self.conn, self.settings)
        job = claim(self.conn)
        if job is None:
            return False
        start = time.perf_counter()
        try:
            result = self.process(job)
            log.info("job %s concluído em %.1fs: %s", job["id"], time.perf_counter() - start, result)
        except JobError as error:
            fail(self.conn, job["id"], str(error))
            log.info("job %s recusado: %s", job["id"], error)
        except Exception:
            log.exception("job %s falhou", job["id"])
            fail(self.conn, job["id"], "Erro interno ao processar o job.")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Processa os jobs do modo exploration.")
    parser.add_argument("--config", type=Path, required=True, help="configuração do experimento publicado")
    parser.add_argument("--once", action="store_true", help="processa no máximo um job e termina")
    parser.add_argument("--poll", type=float, default=2.0, help="intervalo entre consultas, em segundos")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

    settings = Settings.from_env()
    while True:
        try:
            with psycopg.connect(os.environ["SUPABASE_DATABASE_URL"], autocommit=True, connect_timeout=20,
                                 keepalives_idle=30) as conn:
                worker = Worker(conn, args.config, settings)
                log.info("worker conectado (amostra %s)", worker.sample_id)
                while True:
                    processed = worker.run_once()
                    if args.once:
                        return
                    if not processed:
                        time.sleep(args.poll)
        except psycopg.OperationalError as error:
            # Network failure: a job left in 'running' is recovered by housekeeping after the stale timeout.
            if args.once:
                raise
            log.warning("conexão perdida (%s); nova tentativa em %ss", str(error).splitlines()[0], RECONNECT_SECONDS)
            time.sleep(RECONNECT_SECONDS)


if __name__ == "__main__":
    main()
