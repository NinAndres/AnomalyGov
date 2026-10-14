import hashlib
from pathlib import Path

import pandas as pd

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


def classify_favored(codes: pd.Series) -> pd.Series:
    types = pd.Series("other", index=codes.index)
    unmatched = pd.Series(True, index=codes.index)
    for favored_type, pattern in FAVORED_TYPE_PATTERNS:
        match = unmatched & codes.str.fullmatch(pattern)
        types[match] = favored_type
        unmatched &= ~match
    return types


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
