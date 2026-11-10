import io
import json
import logging
import urllib.error
from datetime import date

import numpy as np
import pytest

from anomalygov_ml.portal.bases import (
    BASES, classify_favored, compute_features, display_values, fetch, months_between, normalize, parse_date,
    parse_value, pick, travel_params,
)
from anomalygov_ml.portal.client import MAX_RETRIES, PortalClient, PortalError
from anomalygov_ml.portal.register import definition

KEY = "segredo-de-teste"


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://example", code, "erro", headers or {}, None)


def client_with(responses, requests_per_minute=60):
    """Client whose opener returns (or raises) the given responses in order, recording the requests."""
    clock = FakeClock()
    sent = []

    def opener(request, timeout):
        sent.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return Response(json.dumps(response).encode("utf-8"))

    client = PortalClient(KEY, requests_per_minute, base_url="https://portal.test/api-de-dados", opener=opener,
                          sleep=clock.sleep, clock=clock.clock)
    return client, sent, clock


def test_client_requires_a_key():
    with pytest.raises(PortalError, match="PORTAL_API_KEY"):
        PortalClient("")


def test_client_sends_the_key_only_in_the_header_and_spaces_requests():
    client, sent, clock = client_with([[1], [2], [3]], requests_per_minute=60)
    assert [client.get("/cartoes", {"pagina": i}) for i in (1, 2, 3)] == [[1], [2], [3]]
    assert all(r.get_header("Chave-api-dados") == KEY and KEY not in r.full_url for r in sent)
    assert sent[0].full_url == "https://portal.test/api-de-dados/cartoes?pagina=1"
    assert clock.sleeps == [1.0, 1.0]  # 60 per minute: one second apart
    assert KEY not in repr(client)


def test_client_retries_rate_limit_and_server_errors_with_growing_waits(caplog):
    client, _, clock = client_with([http_error(429), http_error(503), urllib.error.URLError("rede"), ["ok"]],
                                   requests_per_minute=6000)
    with caplog.at_level(logging.WARNING, logger="anomalygov.portal"):
        assert client.get("/viagens", {"pagina": 1}) == ["ok"]
    waits = [s for s in clock.sleeps if s >= 1]
    assert waits == [2.0, 4.0, 8.0]
    assert client.requests == 4
    assert KEY not in caplog.text and "429" in caplog.text


def test_client_honours_retry_after():
    client, _, clock = client_with([http_error(429, {"Retry-After": "30"}), ["ok"]], requests_per_minute=6000)
    client.get("/cartoes", {})
    assert 30.0 in clock.sleeps


def test_client_gives_up_after_the_retries():
    client, _, _ = client_with([http_error(500)] * (MAX_RETRIES + 1), requests_per_minute=6000)
    with pytest.raises(PortalError, match="não respondeu"):
        client.get("/cartoes", {})


@pytest.mark.parametrize("code, message", [(401, "chave"), (403, "chave"), (400, "HTTP 400")])
def test_client_does_not_retry_client_errors(code, message):
    client, _, _ = client_with([http_error(code)], requests_per_minute=6000)
    with pytest.raises(PortalError, match=message) as error:
        client.get("/cartoes", {})
    assert KEY not in str(error.value) and client.requests == 1


def test_pages_stop_at_an_empty_or_short_page():
    client, sent, _ = client_with([[1, 2], [3, 4], [5]], requests_per_minute=6000)
    assert list(client.pages("/cartoes", {"codigoOrgao": "1"})) == [[1, 2], [3, 4], [5]]
    assert [r.full_url.rsplit("pagina=", 1)[1] for r in sent] == ["1", "2", "3"]

    client, sent, _ = client_with([[1, 2], []], requests_per_minute=6000)
    assert list(client.pages("/cartoes", {})) == [[1, 2]]


def test_pages_reject_unexpected_responses():
    client, _, _ = client_with([{"erro": "x"}], requests_per_minute=6000)
    with pytest.raises(PortalError, match="formato"):
        list(client.pages("/cartoes", {}))


@pytest.mark.parametrize("raw, expected", [
    (1234.5, 1234.5), ("1234.56", 1234.56), ("1.234,56", 1234.56), (",87", 0.87), ("R$ 10,00", 10.0),
    ("-5,00", -5.0), (None, None), ("", None), ("abc", None), (True, None), (float("nan"), None),
])
def test_parse_value(raw, expected):
    assert parse_value(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("2025-03-14", date(2025, 3, 14)), ("2025-03-14T10:00:00", date(2025, 3, 14)), ("14/03/2025", date(2025, 3, 14)),
    ("03/2025", date(2025, 3, 1)), (202503, date(2025, 3, 1)), ("202503", date(2025, 3, 1)), (None, None),
    ("ontem", None), (202513, None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("document, expected", [
    ("12.345.678/0001-90", "company"), ("***.456.789-**", "individual"), ("123.456.789-01", "individual"),
    ("170013", "management_unit"), (None, "other"), ("EX123", "other"),
])
def test_classify_favored(document, expected):
    assert classify_favored(document) == expected
    assert classify_favored(document, always_individual=True) == "individual"


def test_months_and_travel_params():
    assert months_between("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]
    # The API rejects ranges longer than one month ("O período deve ser de no máximo 1 mês."), also for the return.
    assert travel_params(date(2025, 12, 1), date(2025, 12, 31)) == [
        {"dataIdaDe": "01/12/2025", "dataIdaAte": "31/12/2025", "dataRetornoDe": "01/12/2025",
         "dataRetornoAte": "31/12/2025"},
        {"dataIdaDe": "01/12/2025", "dataIdaAte": "31/12/2025", "dataRetornoDe": "01/01/2026",
         "dataRetornoAte": "31/01/2026"},
    ]


def test_missing_markers_and_sentinel_dates_are_treated_as_missing():
    assert pick({"a": {"b": "Sem informação"}}, "a.b") is None
    assert pick({"tipo": "Sem Informação"}, "tipo") is None
    assert parse_date("1900-01-01") is None


def test_classified_card_expenses_fall_back_to_the_statement_month():
    # Seen in the API: classified expenses come with "Sem informação" in the date and the establishment.
    base = BASES["portal_cards"]
    item = {"id": 1, "mesExtrato": "03/2025", "dataTransacao": "Sem informação", "valorTransacao": "502,10",
            "estabelecimento": {"tipo": "Sem Informação", "nome": "Sem informação"}, "unidadeGestora": unit()}
    df, excluded = normalize(base, [item])
    assert sum(excluded.values()) == 0
    assert df.loc[0, "date"] == "2025-03-01" and df.loc[0, "value"] == 502.10
    assert df.loc[0, "favored_type"] == "other" and df.loc[0, "favored_name"] is None


def unit(code="170013"):
    return {"codigo": code, "nome": f"UG {code}"}


def sample_item(base_name: str, i: int) -> dict:
    """A record shaped like the API response of each base (fields from the Portal OpenAPI specification)."""
    company = {"cnpjFormatado": f"12.345.678/0001-{i % 7:02d}", "nome": f"EMPRESA {i % 7}"}
    person = {"cpfFormatado": f"***.{i % 5:03d}.789-**", "nome": f"PESSOA {i % 5}"}
    supplier = company if i % 3 else person
    value = 100.0 + 10 * i + (5000 if i == 0 else 0)
    day = f"2025-03-{1 + i % 28:02d}"
    return {
        "portal_payments": lambda: {
            "anoMes": 202503, "codigoPessoa": supplier.get("cnpjFormatado") or supplier["cpfFormatado"],
            "nomePessoa": supplier["nome"], "codigoUG": "17001" + str(i % 2), "nomeUG": "UG", "valor": value,
            "siglaUFPessoa": "DF"},
        "portal_cards": lambda: {
            "id": i, "dataTransacao": f"{1 + i % 28:02d}/03/2025", "valorTransacao": f"{value:.2f}".replace(".", ","),
            "tipoCartao": {"descricao": "Cartão de Pagamento do Governo Federal"}, "estabelecimento": supplier,
            "unidadeGestora": unit(), "portador": {"cpfFormatado": "***.111.222-**", "nome": f"SERVIDOR {i % 4}"}},
        "portal_travel": lambda: {
            "id": i, "situacao": "Realizada", "beneficiario": {"cpfFormatado": "***.111.222-**", "nome": "SERVIDOR"},
            "unidadeGestoraResponsavel": unit(), "dataInicioAfastamento": day, "dataFimAfastamento": "2025-03-29",
            "valorTotalViagem": value, "valorTotalDiarias": value / 2, "valorTotalPassagem": value / 4},
        "portal_contracts": lambda: {
            "id": i, "modalidadeCompra": "Pregão", "unidadeGestora": unit(), "dataAssinatura": day,
            "dataInicioVigencia": day, "dataFimVigencia": "2026-03-01", "fornecedor": supplier,
            "valorInicialCompra": value, "valorFinalCompra": value * 1.1},
        "portal_biddings": lambda: {
            "id": i, "modalidadeLicitacao": "Pregão" if i % 2 else "Dispensa", "situacaoCompra": "Publicada",
            "dataAbertura": day, "dataResultadoCompra": "2025-04-10", "valor": value, "unidadeGestora": unit()},
        "portal_agreements": lambda: {
            "id": i, "situacao": "Em execução", "dataReferencia": day, "dataInicioVigencia": day,
            "dataFinalVigencia": "2027-01-01", "convenente": supplier, "unidadeGestora": unit(), "valor": value,
            "valorLiberado": value / 3, "valorContrapartida": None},
    }[base_name]()


@pytest.mark.parametrize("name", list(BASES))
def test_every_base_normalizes_and_builds_finite_features(name):
    base = BASES[name]
    items = [sample_item(name, i) for i in range(40)]
    df, excluded = normalize(base, items)
    assert len(df) == 40 and sum(excluded.values()) == 0
    features = compute_features(base, df)
    assert list(features.columns) == list(base.feature_columns)
    assert np.isfinite(features.to_numpy()).all()
    values = list(display_values(base, df))
    assert set(values[0]) == set(base.display_columns)
    json.dumps(values)  # stored as jsonb


@pytest.mark.parametrize("name", [n for n in BASES if BASES[n].favored])
def test_names_of_individuals_are_never_kept(name):
    base = BASES[name]
    df, _ = normalize(base, [sample_item(name, i) for i in range(40)])
    rows = list(display_values(base, df))
    individuals = [r for r in rows if r["favored_type"] == "individual"]
    assert individuals and all(r["favored_name"] is None for r in individuals)
    text = json.dumps(rows, ensure_ascii=False)
    assert "PESSOA" not in text and "SERVIDOR" not in text and "***" not in text
    assert any(r["favored_name"] for r in rows) == (name != "portal_travel")


def test_normalize_excludes_duplicates_missing_dates_and_non_positive_values():
    base = BASES["portal_contracts"]
    good = sample_item("portal_contracts", 1)
    items = [good, dict(good), {**sample_item("portal_contracts", 2), "dataAssinatura": None, "dataInicioVigencia": None},
             {**sample_item("portal_contracts", 3), "valorFinalCompra": 0, "valorInicialCompra": -1},
             {**sample_item("portal_contracts", 4), "valorFinalCompra": None}]
    df, excluded = normalize(base, items)
    assert excluded == {"duplicate": 1, "missing_date": 1, "non_positive_value": 1}
    # The final value falls back to the initial one when missing.
    assert sorted(df["portal_id"]) == ["1", "4"] and df.set_index("portal_id").loc["4", "value"] == 140.0


def test_features_are_relative_to_the_cut():
    base = BASES["portal_cards"]
    df, _ = normalize(base, [sample_item("portal_cards", i) for i in range(40)])
    features = compute_features(base, df)
    outlier = df.index[df["portal_id"] == "0"][0]
    assert features.loc[outlier, "value_vs_unit"] == features["value_vs_unit"].max()
    assert set(features["weekend"]) == {0.0, 1.0}
    assert features["holder_log_count"].round(6).eq(round(np.log1p(10), 6)).all()


def test_fetch_goes_month_by_month_and_stops_at_the_cap():
    base = BASES["portal_cards"]
    pages = [[{"id": 1}, {"id": 2}], [{"id": 3}], [{"id": 4}, {"id": 5}], [{"id": 6}]]
    client, sent, _ = client_with(list(pages), requests_per_minute=6000)
    progress = []
    result = fetch(client, base, "26000", "2025-01", "2025-02", 100, lambda m, n: progress.append((m, n)))
    assert [i["id"] for i in result.items] == [1, 2, 3, 4, 5, 6] and not result.truncated
    assert result.requests == 4 and progress[-1] == ("2025-02", 6)
    assert "codigoOrgao=26000" in sent[0].full_url and "mesExtratoInicio=01%2F2025" in sent[0].full_url
    assert "mesExtratoInicio=02%2F2025" in sent[2].full_url

    # Records beyond the cap: truncated, which takes one request past the page that reached it.
    client, sent, _ = client_with(list(pages), requests_per_minute=6000)
    result = fetch(client, base, "26000", "2025-01", "2025-02", 3)
    assert [i["id"] for i in result.items] == [1, 2, 3] and result.truncated and len(sent) == 3


def test_fetch_is_not_truncated_when_the_cut_has_exactly_the_cap():
    base = BASES["portal_cards"]
    pages = [[{"id": 1}, {"id": 2}], [{"id": 3}], [{"id": 4}, {"id": 5}], [{"id": 6}]]
    client, sent, _ = client_with(list(pages), requests_per_minute=6000)
    result = fetch(client, base, "26000", "2025-01", "2025-02", 6)
    assert [i["id"] for i in result.items] == [1, 2, 3, 4, 5, 6] and not result.truncated and len(sent) == 4


def test_definition_requires_one_agency_and_a_bounded_period():
    agencies = [{"value": "26000", "label": "Ministério (26000)"}]
    d = definition(BASES["portal_travel"], agencies, "2026-10")
    agency, period = d["filters"]
    assert agency == {"name": "agency_code", "type": "select", "label": "Órgão", "options": agencies,
                      "required": True, "maxSelected": 1}
    assert period["type"] == "month_range" and period["required"] and period["maxMonths"] == 12
    assert (period["min"], period["max"]) == ("2015-01", "2026-10")
    assert d["feature_columns"] == list(BASES["portal_travel"].feature_columns)
    # Bases no longer updated by the Portal stop at their last month with data.
    assert definition(BASES["portal_biddings"], agencies, "2026-10")["filters"][1]["max"] == "2024-04"
