"""Register the Portal API bases in the `sources` table, so the application offers them (decision 0014).

Usage: python -m anomalygov_ml.portal.register

The agency options are the agencies of the management units in the local database (DATABASE_URL), that is,
the agencies that paid something in the ingested data. The definitions are written to SUPABASE_DATABASE_URL.
Re-running updates the definitions and moves the last available month to the current one.
"""

import argparse
import os
from datetime import date
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from anomalygov_ml.portal.bases import BASES, PortalBase

MAX_MONTHS = 12


def agency_options(conn: psycopg.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        "SELECT DISTINCT agency_code, agency_name FROM management_units WHERE agency_code IS NOT NULL ORDER BY 2, 1"
    ).fetchall()
    return [{"value": code, "label": f"{name} ({code})"} for code, name in rows]


def definition(base: PortalBase, agencies: list[dict[str, str]], last_month: str) -> dict[str, Any]:
    return {
        "name": base.name,
        "label": base.label,
        "filters": [
            {"name": "agency_code", "type": "select", "label": "Órgão", "options": agencies,
             "required": True, "maxSelected": 1},
            {"name": "period", "type": "month_range", "label": base.period_label, "min": base.first_month,
             "max": last_month, "required": True, "maxMonths": MAX_MONTHS},
        ],
        "display_columns": list(base.display_columns),
        "feature_columns": list(base.feature_columns),
    }


def register(target: psycopg.Connection, agencies: list[dict[str, str]], last_month: str) -> list[str]:
    with target.transaction():
        for base in BASES.values():
            d = definition(base, agencies, last_month)
            target.execute(
                """INSERT INTO sources (name, label, filters, display_columns, feature_columns, kind)
                   VALUES (%s, %s, %s, %s, %s, 'portal')
                   ON CONFLICT (name) DO UPDATE SET label = EXCLUDED.label, filters = EXCLUDED.filters,
                       display_columns = EXCLUDED.display_columns, feature_columns = EXCLUDED.feature_columns,
                       kind = EXCLUDED.kind, updated_at = now()""",
                (d["name"], d["label"], Jsonb(d["filters"]), Jsonb(d["display_columns"]),
                 Jsonb(d["feature_columns"])),
            )
    return list(BASES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Registra as bases da API do Portal na tabela sources.")
    parser.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"]) as source:
        agencies = agency_options(source)
    if not agencies:
        raise SystemExit("nenhum órgão em management_units no banco local; rode a ingestão antes")
    with psycopg.connect(os.environ["SUPABASE_DATABASE_URL"], autocommit=True) as target:
        names = register(target, agencies, date.today().strftime("%Y-%m"))
    print(f"{len(names)} bases registradas ({', '.join(names)}) com {len(agencies)} órgãos")


if __name__ == "__main__":
    main()
