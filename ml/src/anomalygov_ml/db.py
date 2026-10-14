import io
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

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


@contextmanager
def id_table(conn: psycopg.Connection, name: str, ids: Iterable[int]) -> Iterator[None]:
    """Temporary table holding the given ids, dropped on exit.

    The table is dropped explicitly because, when the connection is already inside a transaction,
    conn.transaction() is only a savepoint and ON COMMIT DROP would not fire.
    """
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE {name} (id bigint PRIMARY KEY)")
        with cur.copy(f"COPY {name} (id) FROM STDIN") as copy:
            for id_ in ids:
                copy.write_row((int(id_),))
        yield
        cur.execute(f"DROP TABLE {name}")
