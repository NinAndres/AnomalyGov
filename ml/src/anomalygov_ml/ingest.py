"""Ingest raw Portal files into the database.

Usage: python -m anomalygov_ml.ingest [--source payments] FILE [FILE ...]
"""

import argparse
import calendar
import hashlib
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from anomalygov_ml.sources.base import SourceAdapter
from anomalygov_ml.sources.payments import PaymentsAdapter

ADAPTERS: dict[str, SourceAdapter] = {adapter.name: adapter for adapter in (PaymentsAdapter(),)}

STAGE_COLUMNS = (
    "favored_hash",
    "favored_type",
    "favored_code",
    "favored_name",
    "uf",
    "municipality",
    "superior_agency_code",
    "superior_agency_name",
    "agency_code",
    "agency_name",
    "management_unit_code",
    "management_unit_name",
    "reference_month",
    "amount",
)


@dataclass(frozen=True)
class FileInfo:
    sha256: str
    row_count: int
    period_start: date
    period_end: date


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe(df: pd.DataFrame, sha256: str) -> FileInfo:
    first, last = min(df["reference_month"]), max(df["reference_month"])
    period_end = last.replace(day=calendar.monthrange(last.year, last.month)[1])
    return FileInfo(sha256, len(df), first, period_end)


def ingest_file(conn: psycopg.Connection, adapter: SourceAdapter, path: Path) -> int | None:
    """Load one file in a single transaction. Returns the dataset_files id, or None if already ingested."""
    sha256 = file_sha256(path)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT id FROM dataset_files WHERE sha256 = %s", (sha256,))
        if cur.fetchone():
            return None

        df = adapter.parse(path)
        info = describe(df, sha256)
        df, excluded = adapter.exclude(df)
        cur.execute(
            """INSERT INTO dataset_files
                   (source, file_name, sha256, row_count, loaded_row_count, excluded_rows, period_start, period_end)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (adapter.name, path.name, info.sha256, info.row_count, len(df), Jsonb(excluded),
             info.period_start, info.period_end),
        )
        file_id = cur.fetchone()[0]

        cur.execute(
            f"CREATE TEMP TABLE stage ({', '.join(f'{c} text' for c in STAGE_COLUMNS)}) ON COMMIT DROP"
        )
        stage = df[list(STAGE_COLUMNS)].astype(object).where(df[list(STAGE_COLUMNS)].notna(), None)
        with cur.copy(f"COPY stage ({', '.join(STAGE_COLUMNS)}) FROM STDIN") as copy:
            for row in stage.itertuples(index=False, name=None):
                copy.write_row(row)

        cur.execute(
            """INSERT INTO management_units
                   (code, name, agency_code, agency_name, superior_agency_code, superior_agency_name)
               SELECT DISTINCT ON (management_unit_code) management_unit_code, management_unit_name,
                      agency_code, agency_name, superior_agency_code, superior_agency_name
               FROM stage
               ON CONFLICT (code) DO UPDATE SET
                   name = EXCLUDED.name, agency_code = EXCLUDED.agency_code, agency_name = EXCLUDED.agency_name,
                   superior_agency_code = EXCLUDED.superior_agency_code,
                   superior_agency_name = EXCLUDED.superior_agency_name"""
        )
        cur.execute(
            """INSERT INTO favored (key_hash, favored_type, code, name)
               SELECT DISTINCT ON (favored_hash) decode(favored_hash, 'hex'), favored_type, favored_code, favored_name
               FROM stage
               ON CONFLICT (key_hash) DO NOTHING"""
        )
        cur.execute(
            """INSERT INTO payments
                   (dataset_file_id, reference_month, favored_id, management_unit_code, uf, municipality, amount)
               SELECT %s, s.reference_month::date, f.id, s.management_unit_code, s.uf, s.municipality,
                      s.amount::numeric
               FROM stage s JOIN favored f ON f.key_hash = decode(s.favored_hash, 'hex')""",
            (file_id,),
        )
        if cur.rowcount != len(df):
            raise RuntimeError(f"{path.name}: {cur.rowcount} linhas gravadas, esperado {len(df)}")
        return file_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingere arquivos brutos do Portal da Transparência no banco.")
    parser.add_argument("--source", choices=sorted(ADAPTERS), default="payments")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()

    adapter = ADAPTERS[args.source]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for path in args.files:
            file_id = ingest_file(conn, adapter, path)
            status = "já ingerido, ignorado" if file_id is None else f"dataset_files.id={file_id}"
            print(f"{path.name}: {status}")


if __name__ == "__main__":
    main()
