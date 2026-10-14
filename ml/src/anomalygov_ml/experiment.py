"""Batch execution of the three algorithms in `experiment` mode (decisions 0005 and 0006).

Usage: python -m anomalygov_ml.experiment CONFIG [--parts main,parameter,artifact,data_stability,scalability]

Writes samples, runs and scores to the local database (DATABASE_URL). Each run is committed on its own,
so an interrupted experiment keeps the runs already finished.
"""

import argparse
import hashlib
import itertools
import os
import platform
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psycopg
import scipy
import sklearn
from psycopg.types.json import Jsonb
from sklearn.preprocessing import RobustScaler

from anomalygov_ml import metrics
from anomalygov_ml.ingest import ADAPTERS
from anomalygov_ml.models import DETECTORS, N_JOBS
from anomalygov_ml.sampling import stratified_sample

PARTS = ("main", "parameter", "artifact", "data_stability", "scalability")
ALGORITHMS = ("isolation_forest", "lof", "one_class_svm")


@dataclass(frozen=True)
class Sample:
    id: int
    ids: list[int]
    features: np.ndarray  # unscaled, rows in `ids` order


def environment() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "n_jobs": N_JOBS,
    }


def parameter_grid(spec: dict[str, list]) -> list[dict[str, Any]]:
    return [dict(zip(spec, values)) for values in itertools.product(*spec.values())]


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def insert_run(
    cur: psycopg.Cursor, experiment: str, config_sha256: str, purpose: str, algorithm: str,
    params: dict[str, Any], random_state: int | None, feature_columns: list[str], train_sample_id: int,
    scored_sample_id: int | None, n_train: int, n_scored: int, fit_seconds: float, score_seconds: float,
    environment: dict[str, Any], subset: dict[str, Any] | None = None, mode: str = "experiment",
    job_id: str | None = None,
) -> int:
    """Record one algorithm execution (AGENTS.md, section 7) and return its id."""
    cur.execute(
        """INSERT INTO runs (experiment, config_sha256, mode, purpose, algorithm, params, random_state,
                             feature_columns, train_sample_id, scored_sample_id, n_train, n_scored,
                             fit_seconds, score_seconds, environment, subset, job_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            experiment, config_sha256, mode, purpose, algorithm, Jsonb(params), random_state, feature_columns,
            train_sample_id, scored_sample_id, n_train, n_scored, fit_seconds, score_seconds, Jsonb(environment),
            Jsonb(subset) if subset is not None else None, job_id,
        ),
    )
    return cur.fetchone()[0]


class Experiment:
    def __init__(self, conn: psycopg.Connection, config_path: Path):
        raw = config_path.read_bytes()
        self.config = tomllib.loads(raw.decode("utf-8"))
        self.config_sha256 = hashlib.sha256(raw).hexdigest()
        self.conn = conn
        self.adapter = ADAPTERS[self.config["source"]]
        self.environment = environment()
        self._population: pd.DataFrame | None = None

    def population(self) -> pd.DataFrame:
        if self._population is None:
            self._population = self.adapter.load_population(self.conn)
        return self._population

    def sample(self, seed: int, total: int, floor: int) -> Sample:
        """Return the sample with this design, drawing and storing it the first time."""
        strata = list(self.adapter.strata_columns)
        file_ids = self.conn.execute(
            "SELECT array_agg(id ORDER BY id) FROM dataset_files WHERE source = %s", (self.adapter.name,)
        ).fetchone()[0]
        key = (self.adapter.name, seed, total, floor, strata, file_ids)
        row = self.conn.execute(
            """SELECT id FROM samples WHERE source = %s AND seed = %s AND total = %s AND floor = %s
                   AND strata = %s::text[] AND dataset_file_ids = %s::integer[]""",
            key,
        ).fetchone()
        if row:
            sample_id = row[0]
            ids = [r[0] for r in self.conn.execute(
                "SELECT payment_id FROM sample_records WHERE sample_id = %s ORDER BY payment_id", (sample_id,)
            )]
        else:
            population = self.population()
            drawn = stratified_sample(population, strata, total, floor, seed)
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO samples (source, seed, total, floor, strata, dataset_file_ids,
                                            population_size, sample_size)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (*key, len(population), len(drawn)),
                )
                sample_id = cur.fetchone()[0]
                with cur.copy("COPY sample_records (sample_id, payment_id, weight) FROM STDIN") as copy:
                    for payment_id, weight in zip(drawn["id"], drawn["weight"]):
                        copy.write_row((sample_id, int(payment_id), float(weight)))
            ids = drawn["id"].tolist()
        features = self.adapter.load_features(self.conn, ids)[list(self.adapter.feature_columns)].to_numpy()
        log(f"amostra {sample_id} (semente {seed}, total {total}, piso {floor}): {len(ids)} registros")
        return Sample(sample_id, ids, features)

    def execute(
        self, purpose: str, algorithm: str, params: dict[str, Any], train: Sample, scored: Sample | None
    ) -> tuple[int, np.ndarray]:
        """Fit on `train`, score `scored` (or `train` itself, without storing scores, when None)."""
        params = dict(params)
        random_state = params.pop("random_state", None)
        detector = DETECTORS[algorithm](params, random_state)
        external = scored is not None and scored.id != train.id
        if algorithm == "lof" and external:
            detector.params["novelty"] = True  # LOF must be fitted in novelty mode to score other records

        scaler = RobustScaler().fit(train.features)
        X_train = scaler.transform(train.features)
        X_scored = scaler.transform(scored.features) if external else X_train

        start = time.perf_counter()
        detector.fit(X_train)
        fit_seconds = time.perf_counter() - start
        start = time.perf_counter()
        scores = detector.score(X_scored)
        score_seconds = time.perf_counter() - start

        with self.conn.transaction(), self.conn.cursor() as cur:
            run_id = insert_run(
                cur, self.config["name"], self.config_sha256, purpose, algorithm, detector.resolved_params,
                random_state, list(self.adapter.feature_columns), train.id, scored.id if scored else None,
                len(X_train), len(X_scored), fit_seconds, score_seconds, self.environment,
            )
            if scored is not None:
                normalized = metrics.normalize(scores)
                with cur.copy("COPY run_scores (run_id, payment_id, raw_score, normalized_score) FROM STDIN") as copy:
                    for payment_id, raw, norm in zip(scored.ids, scores, normalized):
                        copy.write_row((run_id, payment_id, float(raw), float(norm)))

        shown = {k: v for k, v in detector.resolved_params.items() if k in (*params, "n_neighbors")}
        flagged = int(metrics.flagged(scores, self.config["p"][0]).sum())
        log(f"run {run_id} {purpose}/{algorithm} {shown} n={len(X_train)} "
            f"treino={fit_seconds:.1f}s pontuação={score_seconds:.1f}s sinalizados@p={flagged}")
        return run_id, scores

    def try_execute(self, *args) -> None:
        try:
            self.execute(*args)
        except MemoryError:
            log(f"sem memória em {args[0]}/{args[1]} {args[2]}: execução não registrada")

    def run(self, parts: tuple[str, ...]) -> None:
        cfg = self.config
        design = cfg["sample"]
        main = self.sample(design["seed"], design["total"], design["floor"])

        if "main" in parts:
            scores = {alg: self.execute("main", alg, cfg["main"][alg], main, main)[1] for alg in ALGORITHMS}
            for p in cfg["p"]:
                pairs = itertools.combinations(ALGORITHMS, 2)
                summary = ", ".join(
                    f"{a}×{b}={metrics.jaccard(metrics.flagged(scores[a], p), metrics.flagged(scores[b], p)):.3f}"
                    for a, b in pairs
                )
                log(f"concordância (Jaccard) p={p}: {summary}")

        if "parameter" in parts:
            for alg, spec in cfg["parameter"].items():
                base = cfg["main"][alg]
                for combo in parameter_grid(spec):
                    params = {**base, **combo}
                    if params != base:
                        self.try_execute("parameter", alg, params, main, main)

        if "artifact" in parts:
            for alg, spec in cfg["artifact"].items():
                for params in parameter_grid(spec):
                    self.try_execute("artifact", alg, params, main, main)

        if "data_stability" in parts:
            for seed in cfg["data_stability"]["seeds"]:
                train = self.sample(seed, design["total"], design["floor"])
                for alg in ALGORITHMS:
                    self.try_execute("data_stability", alg, cfg["main"][alg], train, main)

        if "scalability" in parts:
            spec = cfg["scalability"]
            for size in spec["sizes"]:
                floor = round(design["floor"] * size / design["total"])
                for repetition in range(1, spec["repetitions"] + 1):
                    sample = self.sample(1000 + repetition, size, floor)
                    for alg in ALGORITHMS:
                        if alg == "lof" and size > spec["lof_max_size"]:
                            continue
                        self.try_execute("scalability", alg, cfg["main"][alg], sample, None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa um experimento definido em ml/experiments/configs/.")
    parser.add_argument("config", type=Path)
    parser.add_argument("--parts", default=",".join(PARTS), help=f"subconjunto de {','.join(PARTS)}")
    args = parser.parse_args()
    parts = tuple(args.parts.split(","))
    unknown = set(parts) - set(PARTS)
    if unknown:
        parser.error(f"partes desconhecidas: {', '.join(sorted(unknown))}")

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        Experiment(conn, args.config).run(parts)


if __name__ == "__main__":
    main()
