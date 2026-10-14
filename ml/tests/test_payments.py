from datetime import date

import pandas as pd
import pytest

from anomalygov_ml.ingest import describe, file_sha256
from anomalygov_ml.sources.payments import RAW_COLUMNS, PaymentsAdapter, favored_key

ORG = '"26000";"Ministério da Educação";"26291";"CAPES";"154003";"FUND.COORD.DE APERF.DE PESSOAL NIVEL SUPERIOR"'


def row(code, name, uf="SP", municipality="SÃO PAULO", amount="700"):
    return f'"{code}";"{name}";"{uf}";"{municipality}";{ORG};"01/2025";"{amount}"'


@pytest.fixture
def csv_path(tmp_path):
    lines = [
        ";".join(f'"{c}"' for c in RAW_COLUMNS),
        row("***.123.456-**", "MARIA DA SILVA"),
        row("***.123.456-**", "JOÃO SOUZA", amount="1100,5000"),
        row("04890965000158", "EMPRESA LTDA", amount="-8,5300"),
        row("160356", "12º BATALHAO", uf="RS", municipality="ALEGRETE"),
        row("EXOTT1000", "ONTARIO INC", uf="EX", municipality="Exterior"),
        row("-11", "Sigiloso", uf="-1", municipality="Sem informação"),
        row("RB0003866", "BANCO CENTRAL DO BRASIL", uf="DF", municipality="BRASÍLIA", amount=",8700"),
    ]
    path = tmp_path / "202501_RecebimentosRecursosPorFavorecido.csv"
    path.write_bytes("\r\n".join(lines).encode("latin-1"))
    return path


def test_parse_normalizes_values_and_dates(csv_path):
    df = PaymentsAdapter().parse(csv_path)
    assert len(df) == 7
    assert df["amount"].tolist()[:3] == ["700", "1100.5000", "-8.5300"]
    assert df["amount"].iloc[-1] == "0.8700"
    assert set(df["reference_month"]) == {date(2025, 1, 1)}
    assert df.loc[0, "municipality"] == "SÃO PAULO"


def test_parse_classifies_favored(csv_path):
    df = PaymentsAdapter().parse(csv_path)
    assert df["favored_type"].tolist() == [
        "individual", "individual", "company", "management_unit", "foreign", "special", "other",
    ]


def test_parse_marks_missing_location_as_null(csv_path):
    df = PaymentsAdapter().parse(csv_path)
    special = df[df["favored_type"] == "special"].iloc[0]
    assert pd.isna(special["uf"]) and pd.isna(special["municipality"])
    foreign = df[df["favored_type"] == "foreign"].iloc[0]
    assert foreign["uf"] == "EX"


def test_parse_hides_individuals_and_keeps_distinct_hashes(csv_path):
    df = PaymentsAdapter().parse(csv_path)
    individuals = df[df["favored_type"] == "individual"]
    assert individuals["favored_code"].isna().all()
    assert individuals["favored_name"].isna().all()
    # Same masked CPF, different people.
    assert individuals["favored_hash"].nunique() == 2
    assert individuals["favored_hash"].iloc[0] == favored_key("***.123.456-**", "MARIA DA SILVA", "individual")


def test_company_hash_depends_only_on_code():
    assert favored_key("04890965000158", "A", "company") == favored_key("04890965000158", "B", "company")


def test_parse_rejects_unexpected_header(tmp_path):
    path = tmp_path / "202501_Despesas.csv"
    path.write_bytes('"Ano e mês do lançamento";"Valor Pago (R$)"\r\n"2025/01";"1,00"'.encode("latin-1"))
    with pytest.raises(ValueError, match="cabeçalho inesperado"):
        PaymentsAdapter().parse(path)


def test_parse_rejects_invalid_amount(tmp_path, csv_path):
    content = csv_path.read_bytes().replace(b'"700"', b'"7,00,0"', 1)
    path = tmp_path / "bad.csv"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="valores inválidos"):
        PaymentsAdapter().parse(path)


def test_describe_reports_rows_and_full_month_period(csv_path):
    df = PaymentsAdapter().parse(csv_path)
    info = describe(df, file_sha256(csv_path))
    assert info.row_count == 7
    assert (info.period_start, info.period_end) == (date(2025, 1, 1), date(2025, 1, 31))
    assert len(info.sha256) == 64


def test_exclude_removes_treasury_negative_and_zero(csv_path):
    adapter = PaymentsAdapter()
    df = adapter.parse(csv_path)
    df.loc[df["favored_type"] == "foreign", "amount"] = "0.0000"
    kept, excluded = adapter.exclude(df)
    assert excluded == {"treasury_operation": 1, "negative_amount": 1, "zero_amount": 1}
    assert len(kept) == len(df) - 3
    assert set(kept["favored_type"]) == {"individual", "management_unit", "special"}
    assert (pd.to_numeric(kept["amount"]) > 0).all()


def test_exclude_counts_each_row_once(csv_path):
    adapter = PaymentsAdapter()
    df = adapter.parse(csv_path)
    df.loc[df["favored_type"] == "other", "amount"] = "-1.00"  # treasury and negative at once
    _, excluded = adapter.exclude(df)
    assert excluded["treasury_operation"] == 1
    assert sum(excluded.values()) == 2
