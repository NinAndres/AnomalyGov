import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from anomalygov_ml.db import id_table, read_query
from anomalygov_ml.sources.base import FilterSpec, SourceAdapter

RAW_COLUMNS = {
    "Código Favorecido": "favored_code",
    "Nome Favorecido": "favored_name",
    "Sigla UF": "uf",
    "Nome Município": "municipality",
    "Código Órgão Superior": "superior_agency_code",
    "Nome Órgão Superior": "superior_agency_name",
    "Código Órgão": "agency_code",
    "Nome Órgão": "agency_name",
    "Código Unidade Gestora": "management_unit_code",
    "Nome Unidade Gestora": "management_unit_name",
    "Ano e mês do lançamento": "reference_month",
    "Valor Recebido": "amount",
}

# Order matters: first match wins. Anything else is "other" (e.g. Treasury codes RB..., TN...).
FAVORED_TYPE_PATTERNS = (
    ("individual", r"\*{3}\.\d{3}\.\d{3}-\*{2}"),  # CPF already masked by the Portal
    ("company", r"\d{14}"),  # CNPJ
    ("management_unit", r"\d{6}"),  # another federal management unit
    ("foreign", r"EX\w+"),
    ("special", r"-\d+"),  # -1 sem informação, -11 sigiloso, -13 folha de pagamento
)

MISSING_MARKERS = {"-1", "Sem informação"}

# Decision 0005. All statistics are computed over the whole of 2025, not only over the sample.
FEATURE_COLUMNS = (
    "log_amount",  # ln(1 + amount)
    "amount_vs_ug",  # log_amount minus the median log_amount of the paying management unit
    "amount_vs_favored",  # robust z-score of log_amount within the favored's own records
    "favored_months",  # distinct months in which the favored received
    "favored_ug_count",  # ln(1 + distinct management units that paid the favored)
)
MAD_OFFSET = 0.1  # keeps amount_vs_favored finite when the favored always receives the same amount


def classify_favored(codes: pd.Series) -> pd.Series:
    types = pd.Series("other", index=codes.index)
    unmatched = pd.Series(True, index=codes.index)
    for favored_type, pattern in FAVORED_TYPE_PATTERNS:
        match = unmatched & codes.str.fullmatch(pattern)
        types[match] = favored_type
        unmatched &= ~match
    return types


def compute_features(history: pd.DataFrame, ug_log_median: pd.Series) -> pd.DataFrame:
    """Build the feature matrix from payment rows.

    `history` must hold every payment (id, favored_id, reference_month, management_unit_code, amount)
    of each favored involved; `ug_log_median` maps management_unit_code to its median log_amount.
    Returns one row per payment id, with FEATURE_COLUMNS.
    """
    h = history.copy()
    h["log_amount"] = np.log1p(h["amount"].astype(float))
    by_favored = h.groupby("favored_id")
    median = by_favored["log_amount"].transform("median")
    mad = (h["log_amount"] - median).abs().groupby(h["favored_id"]).transform("median")
    h["amount_vs_favored"] = (h["log_amount"] - median) / (mad + MAD_OFFSET)
    h["amount_vs_ug"] = h["log_amount"] - h["management_unit_code"].map(ug_log_median)
    h["favored_months"] = by_favored["reference_month"].transform("nunique")
    h["favored_ug_count"] = np.log1p(by_favored["management_unit_code"].transform("nunique"))
    return h.set_index("id")[list(FEATURE_COLUMNS)]


def favored_key(code: str, name: str, favored_type: str) -> str:
    # A masked CPF is shared by many people, so the name is needed to tell them apart.
    key = f"{code}|{name}" if favored_type == "individual" else code
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class PaymentsAdapter(SourceAdapter):
    name = "payments"
    filters = (
        FilterSpec("reference_month", "month_range", "Mês de referência"),
        FilterSpec("superior_agency_code", "select", "Órgão superior"),
        FilterSpec("management_unit_code", "select", "Unidade gestora"),
        FilterSpec("uf", "select", "UF"),
        FilterSpec("favored_type", "select", "Tipo de favorecido"),
        FilterSpec("amount", "number_range", "Valor recebido (R$)"),
    )
    display_columns = (
        "reference_month",
        "favored_type",
        "favored_name",
        "superior_agency_name",
        "management_unit_name",
        "uf",
        "municipality",
        "amount",
    )
    strata_columns = ("reference_month", "favored_type")
    feature_columns = FEATURE_COLUMNS

    def parse(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path, sep=";", encoding="latin-1", dtype=str, keep_default_na=False)
        if list(df.columns) != list(RAW_COLUMNS):
            raise ValueError(f"{path.name}: cabeçalho inesperado para a base de pagamentos: {list(df.columns)}")
        df = df.rename(columns=RAW_COLUMNS)

        # Values below 1 come without the leading zero (",8700").
        amount = df["amount"].str.replace(",", ".", regex=False).str.replace(r"^(-?)\.", r"\g<1>0.", regex=True)
        invalid = ~amount.str.fullmatch(r"-?\d+(\.\d+)?")
        if invalid.any():
            raise ValueError(f"{path.name}: {invalid.sum()} valores inválidos em 'Valor Recebido'")
        df["amount"] = amount

        month = pd.to_datetime(df["reference_month"], format="%m/%Y")
        df["reference_month"] = month.dt.date

        for column in ("uf", "municipality"):
            df[column] = df[column].where(~df[column].isin(MISSING_MARKERS), None)

        df["favored_type"] = classify_favored(df["favored_code"])
        df["favored_hash"] = [
            favored_key(code, name, favored_type)
            for code, name, favored_type in zip(df["favored_code"], df["favored_name"], df["favored_type"])
        ]
        individual = df["favored_type"] == "individual"
        df.loc[individual, ["favored_code", "favored_name"]] = None
        return df

    def exclude(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
        # A row is counted under the first reason it matches, so the counts add up to the total removed.
        amount = pd.to_numeric(df["amount"])
        rules = (
            ("treasury_operation", df["favored_type"] == "other"),
            ("negative_amount", amount < 0),
            ("zero_amount", amount == 0),
        )
        keep = pd.Series(True, index=df.index)
        counts = {}
        for reason, match in rules:
            removed = keep & match
            counts[reason] = int(removed.sum())
            keep &= ~removed
        return df[keep].reset_index(drop=True), counts

    def load_population(self, conn: psycopg.Connection) -> pd.DataFrame:
        return read_query(
            conn,
            "SELECT p.id, p.reference_month, f.favored_type FROM payments p JOIN favored f ON f.id = p.favored_id",
            parse_dates=["reference_month"],
        )

    def load_features(self, conn: psycopg.Connection, ids: list[int]) -> pd.DataFrame:
        with id_table(conn, "feature_ids", ids):
            history = read_query(
                conn,
                """SELECT p.id, p.favored_id, p.reference_month, p.management_unit_code, p.amount
                   FROM payments p
                   WHERE p.favored_id IN (SELECT s.favored_id FROM payments s JOIN feature_ids i ON i.id = s.id)""",
                dtype={"management_unit_code": str},
                parse_dates=["reference_month"],
            )
            ug_log_median = read_query(
                conn,
                """SELECT management_unit_code,
                          percentile_cont(0.5) WITHIN GROUP (ORDER BY ln(1 + amount::float8)) AS log_median
                   FROM payments
                   WHERE management_unit_code IN
                         (SELECT s.management_unit_code FROM payments s JOIN feature_ids i ON i.id = s.id)
                   GROUP BY management_unit_code""",
                dtype={"management_unit_code": str},
            ).set_index("management_unit_code")["log_median"]
        return compute_features(history, ug_log_median).loc[list(ids)]
