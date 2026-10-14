"""Publish one experiment from the local database to Supabase (decision 0004).

Usage: python -m anomalygov_ml.publish EXPERIMENT [--scores main,parameter,...]

Copies, in a single transaction on the target, only what the application needs: the main sample with its
payments, favored and management units, the dataset files, every run of the experiment with its metrics and
comparisons, the hypothesis results, and the per-record scores of the runs whose purpose is listed in --scores
(default: main). Ids are preserved, so re-publishing is idempotent; runs and hypothesis results of the
experiment that no longer exist locally are removed from the target. The target must already have the
migrations applied.
Source: DATABASE_URL. Target: SUPABASE_DATABASE_URL.
"""

import argparse
import os

import psycopg
import psycopg.sql

COLUMNS = {
    "dataset_files": "id, source, file_name, sha256, row_count, period_start, period_end, ingested_at, "
                     "loaded_row_count, excluded_rows",
    "management_units": "code, name, agency_code, agency_name, superior_agency_code, superior_agency_name",
    "favored": "id, key_hash, favored_type, code, name",
    "payments": "id, dataset_file_id, reference_month, favored_id, management_unit_code, uf, municipality, amount",
    "samples": "id, source, seed, total, floor, strata, dataset_file_ids, population_size, sample_size, created_at",
    "sample_records": "sample_id, payment_id, weight",
    "runs": "id, experiment, config_sha256, mode, purpose, algorithm, params, random_state, feature_columns, "
            "train_sample_id, scored_sample_id, n_train, n_scored, fit_seconds, score_seconds, environment, "
            "created_at, subset",
    "run_scores": "run_id, payment_id, raw_score, normalized_score",
    "run_metrics": "run_id, p, flagged_count, flagged_share, weighted_flagged_share",
    "run_comparisons": "run_a, run_b, p, jaccard, spearman",
    "hypothesis_units": "id, experiment, hypothesis, unit, measures, created_at",
    "hypothesis_tests": "id, experiment, hypothesis, family, test, variable, n, statistic, effect, ci_low, ci_high, "
                        "p_value, p_adjusted, details, created_at",
}
IDENTITY_TABLES = ("dataset_files", "favored", "payments", "samples", "runs", "hypothesis_units", "hypothesis_tests")
UPSERT = {
    "run_metrics": "ON CONFLICT (run_id, p) DO UPDATE SET flagged_count = EXCLUDED.flagged_count, "
                   "flagged_share = EXCLUDED.flagged_share, weighted_flagged_share = EXCLUDED.weighted_flagged_share",
    "run_comparisons": "ON CONFLICT (run_a, run_b, p) DO UPDATE SET jaccard = EXCLUDED.jaccard, "
                       "spearman = EXCLUDED.spearman",
}


def ids_sql(ids: list[int]) -> str:
    return ",".join(str(int(i)) for i in ids) or "NULL"


def transfer(source: psycopg.Connection, target: psycopg.Connection, table: str, select_sql: str) -> int:
    """Stream the rows of `select_sql` (in COLUMNS order) from source into `table` on the target."""
    columns = COLUMNS[table]
    with target.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE stage_{table} (LIKE {table}) ON COMMIT DROP")
        with source.cursor() as src, src.copy(f"COPY ({select_sql}) TO STDOUT") as out, \
                cur.copy(f"COPY stage_{table} ({columns}) FROM STDIN") as inp:
            for block in out:
                inp.write(block)
        overriding = "OVERRIDING SYSTEM VALUE" if table in IDENTITY_TABLES else ""
        conflict = UPSERT.get(table, "ON CONFLICT DO NOTHING")
        cur.execute(f"INSERT INTO {table} ({columns}) {overriding} SELECT {columns} FROM stage_{table} {conflict}")
        return cur.rowcount


def publish(source: psycopg.Connection, target: psycopg.Connection, experiment: str,
            score_purposes: tuple[str, ...] = ("main",)) -> dict[str, int]:
    runs = source.execute(
        "SELECT id, purpose, train_sample_id, scored_sample_id FROM runs WHERE experiment = %s", (experiment,)
    ).fetchall()
    if not runs:
        raise ValueError(f"nenhuma execução para o experimento {experiment!r}")
    run_ids = [r[0] for r in runs]
    main_samples = {r[3] for r in runs if r[1] == "main"}
    if len(main_samples) != 1:
        raise ValueError(f"esperada uma amostra principal, encontradas {sorted(main_samples)}")
    main_sample = main_samples.pop()
    sample_ids = sorted({r[2] for r in runs} | {r[3] for r in runs if r[3] is not None})
    scored_run_ids = [r[0] for r in runs if r[1] in score_purposes and r[3] == main_sample]

    clash = target.execute(
        f"SELECT id, experiment FROM runs WHERE id IN ({ids_sql(run_ids)}) AND experiment <> %s", (experiment,)
    ).fetchall()
    if clash:
        raise ValueError(f"ids de execução já usados por outro experimento no destino: {clash[:5]}")

    in_sample = f"SELECT payment_id FROM sample_records WHERE sample_id = {main_sample}"
    quoted = psycopg.sql.Literal(experiment).as_string(source)
    file_ids = f"SELECT unnest(dataset_file_ids) FROM samples WHERE id IN ({ids_sql(sample_ids)})"
    steps = [
        ("dataset_files", f"SELECT {COLUMNS['dataset_files']} FROM dataset_files WHERE id IN ({file_ids})"),
        ("management_units", f"""SELECT {COLUMNS['management_units']} FROM management_units WHERE code IN
                                 (SELECT management_unit_code FROM payments WHERE id IN ({in_sample}))"""),
        ("favored", f"""SELECT {COLUMNS['favored']} FROM favored WHERE id IN
                        (SELECT favored_id FROM payments WHERE id IN ({in_sample}))"""),
        ("payments", f"SELECT {COLUMNS['payments']} FROM payments WHERE id IN ({in_sample})"),
        ("samples", f"SELECT {COLUMNS['samples']} FROM samples WHERE id IN ({ids_sql(sample_ids)})"),
        ("sample_records", f"SELECT {COLUMNS['sample_records']} FROM sample_records WHERE sample_id = {main_sample}"),
        ("runs", f"SELECT {COLUMNS['runs']} FROM runs WHERE id IN ({ids_sql(run_ids)})"),
        ("run_scores", f"SELECT {COLUMNS['run_scores']} FROM run_scores WHERE run_id IN ({ids_sql(scored_run_ids)})"),
        ("run_metrics", f"SELECT {COLUMNS['run_metrics']} FROM run_metrics WHERE run_id IN ({ids_sql(run_ids)})"),
        ("run_comparisons", f"""SELECT {COLUMNS['run_comparisons']} FROM run_comparisons
                                WHERE run_a IN ({ids_sql(run_ids)}) AND run_b IN ({ids_sql(run_ids)})"""),
        ("hypothesis_units", f"SELECT {COLUMNS['hypothesis_units']} FROM hypothesis_units WHERE experiment = {quoted}"),
        ("hypothesis_tests", f"SELECT {COLUMNS['hypothesis_tests']} FROM hypothesis_tests WHERE experiment = {quoted}"),
    ]
    written = {}
    with target.transaction():
        # Runs re-executed locally get new ids: drop the stale ones (cascades to their scores and metrics).
        target.execute(
            f"DELETE FROM runs WHERE experiment = %s AND mode = 'experiment' AND id NOT IN ({ids_sql(run_ids)})", (experiment,)
        )
        for table in ("hypothesis_units", "hypothesis_tests"):
            target.execute(f"DELETE FROM {table} WHERE experiment = %s", (experiment,))
        for table, select_sql in steps:
            written[table] = transfer(source, target, table, select_sql)
        for table in IDENTITY_TABLES:
            # Keep the target's own inserts (e.g. exploration runs) after the published ids.
            target.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT coalesce(max(id), 0) + 1 FROM {table}), false)"
            )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica um experimento do banco local no Supabase.")
    parser.add_argument("experiment")
    parser.add_argument("--scores", default="main", help="finalidades cujos escores por registro são publicados")
    args = parser.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as source, \
            psycopg.connect(os.environ["SUPABASE_DATABASE_URL"], autocommit=True) as target:
        written = publish(source, target, args.experiment, tuple(args.scores.split(",")))
        size = target.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    for table, count in written.items():
        print(f"{table}: {count} linhas novas ou atualizadas")
    print(f"tamanho do banco de destino: {size}")


if __name__ == "__main__":
    main()
