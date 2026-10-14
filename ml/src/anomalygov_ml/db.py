import io
from collections.abc import Iterable

import pandas as pd
import psycopg


def read_query(conn: psycopg.Connection, query: str, **read_csv_kwargs) -> pd.DataFrame:
    """Run a SELECT through COPY, which is much faster than fetching rows for millions of records."""
    buffer = io.BytesIO()
    with conn.cursor() as cur, cur.copy(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER)") as copy:
        for block in copy:
            buffer.write(block)
    buffer.seek(0)
    return pd.read_csv(buffer, **read_csv_kwargs)


def create_id_table(conn: psycopg.Connection, name: str, ids: Iterable[int]) -> None:
    """Create a temporary table holding the given ids, dropped at the end of the current transaction."""
    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE {name} (id bigint PRIMARY KEY) ON COMMIT DROP")
        with cur.copy(f"COPY {name} (id) FROM STDIN") as copy:
            for id_ in ids:
                copy.write_row((int(id_),))
