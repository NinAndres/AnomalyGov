"""Bases of the Portal da Transparência API available in the exploration mode (decision 0014).

Each base is declared by a `PortalBase`: the endpoint and its parameters, where the common fields (date, value,
management unit, favored, category) are in the JSON, and optional base-specific features. Normalization,
LGPD handling and the generic features are shared by every base.
"""

import calendar
import hashlib
import math
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from anomalygov_ml.portal.client import PortalClient
from anomalygov_ml.sources.payments import MAD_OFFSET

FIRST_MONTH = "2015-01"
FIRST_VALID_YEAR = 1901  # the Portal uses 1900-01-01 for an unknown date
# Only these favored types have their name shown (LGPD, AGENTS.md section 5.2).
NAMED_TYPES = ("company", "management_unit")
FAVORED_TYPE_LABELS = {
    "individual": "Pessoa física",
    "company": "Pessoa jurídica",
    "management_unit": "Unidade gestora federal",
    "other": "Não identificado",
}


def pick(item: dict[str, Any], path: str) -> Any:
    """Value at a dotted path ("unidadeGestora.codigo"); None when missing or blank."""
    value: Any = item
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    if isinstance(value, str):
        value = value.strip()
        if value.lower().startswith("sem informa"):  # "Sem informação", e.g. classified card expenses
            return None
    return None if value in (None, "") else value


def parse_value(value: Any) -> float | None:
    """Number from the API: plain numbers, "1234.56" or Brazilian "1.234,56"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(value) else None
    text = str(value).strip().replace("R$", "").strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_date(value: Any) -> date | None:
    """Date from the API: ISO, DD/MM/AAAA, MM/AAAA or the integer AAAAMM (first day of the month)."""
    if value is None:
        return None
    parsed = None
    if isinstance(value, int):
        year, month = divmod(value, 100)
        parsed = date(year, month, 1) if 1 <= month <= 12 and year >= 1 else None
    else:
        text = str(value).strip()
        for parse in (lambda t: date.fromisoformat(t[:10]),
                      lambda t: datetime.strptime(t, "%d/%m/%Y").date(),
                      lambda t: datetime.strptime(t, "%m/%Y").date(),
                      lambda t: datetime.strptime(t, "%Y%m").date()):
            try:
                parsed = parse(text)
                break
            except ValueError:
                continue
    return parsed if parsed is not None and parsed.year >= FIRST_VALID_YEAR else None


def classify_favored(document: str | None, always_individual: bool = False) -> str:
    if always_individual:
        return "individual"
    if not document:
        return "other"
    if "*" in document:  # CPF masked by the Portal
        return "individual"
    digits = re.sub(r"\D", "", document)
    return {14: "company", 11: "individual", 6: "management_unit"}.get(len(digits), "other")


def identity_hash(document: str | None, name: str | None, individual: bool) -> str | None:
    # A masked CPF is shared by many people, so the name is needed to tell them apart (as in payments).
    if not document and not name:
        return None
    key = f"{document or ''}|{name or ''}" if individual or not document else document
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def month_bounds(month: str) -> tuple[date, date]:
    year, m = (int(x) for x in month.split("-"))
    return date(year, m, 1), date(year, m, calendar.monthrange(year, m)[1])


def months_between(first: str, last: str) -> list[str]:
    year, month = (int(x) for x in first.split("-"))
    last_year, last_month = (int(x) for x in last.split("-"))
    months = []
    while (year, month) <= (last_year, last_month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


# Each builder returns the parameter sets queried for one month (first and last day). The API accepts date ranges of
# at most one month (checked on 2026-10-27).
PeriodParams = Callable[[date, date], list[dict[str, str]]]


def month_params(start: str, end: str) -> PeriodParams:
    return lambda first, last: [{start: first.strftime("%m/%Y"), end: first.strftime("%m/%Y")}]


def date_params(start: str, end: str) -> PeriodParams:
    return lambda first, last: [{start: first.strftime("%d/%m/%Y"), end: last.strftime("%d/%m/%Y")}]


def travel_params(first: date, last: date) -> list[dict[str, str]]:
    # Trips that start in the month and return in it or in the next one. The return range is also limited to one
    # month, hence two queries.
    next_first = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    next_last = date(next_first.year, next_first.month, calendar.monthrange(next_first.year, next_first.month)[1])
    departure = {"dataIdaDe": first.strftime("%d/%m/%Y"), "dataIdaAte": last.strftime("%d/%m/%Y")}
    return [{**departure, "dataRetornoDe": first.strftime("%d/%m/%Y"), "dataRetornoAte": last.strftime("%d/%m/%Y")},
            {**departure, "dataRetornoDe": next_first.strftime("%d/%m/%Y"),
             "dataRetornoAte": next_last.strftime("%d/%m/%Y")}]


def days_between(item: dict[str, Any], start: str, end: str) -> float | None:
    first, last = parse_date(pick(item, start)), parse_date(pick(item, end))
    if first is None or last is None or last < first:
        return None
    return math.log1p((last - first).days + 1)


def share(item: dict[str, Any], part: str, whole: str) -> float | None:
    numerator, denominator = parse_value(pick(item, part)), parse_value(pick(item, whole))
    if numerator is None or not denominator or denominator <= 0:
        return None
    return numerator / denominator


def weekend(item: dict[str, Any]) -> float | None:
    transaction = parse_date(pick(item, "dataTransacao"))
    return None if transaction is None else float(transaction.weekday() >= 5)


def value_change(item: dict[str, Any]) -> float | None:
    """ln(final value / initial value) of a contract: amendments that raised or cut it."""
    ratio = share(item, "valorFinalCompra", "valorInicialCompra")
    return None if ratio is None or ratio <= 0 else math.log(ratio)


@dataclass(frozen=True)
class Favored:
    documents: tuple[str, ...]  # paths tried in order (CNPJ, CPF)
    name: str
    always_individual: bool = False  # e.g. travellers, who are civil servants


@dataclass(frozen=True)
class Category:
    column: str  # display column, e.g. "purchase_modality"
    path: str


@dataclass(frozen=True)
class Extra:
    """Base-specific feature computed from one record; None is imputed with the median of the cut."""

    name: str
    compute: Callable[[dict[str, Any]], float | None]


@dataclass(frozen=True)
class GroupCount:
    """Feature ln(1 + records of the cut sharing the identity at `documents`/`name`), kept only as a hash."""

    name: str
    documents: tuple[str, ...]
    person_name: str


@dataclass(frozen=True)
class PortalBase:
    name: str
    label: str
    endpoint: str
    agency_param: str
    period: PeriodParams
    dates: tuple[str, ...]  # paths tried in order; the first valid date is used
    values: tuple[str, ...]  # paths tried in order; the first positive value is used
    unit_code: str
    unit_name: str
    portal_id: str | None = None
    category: Category | None = None
    favored: Favored | None = None
    group_counts: tuple[GroupCount, ...] = ()
    extras: tuple[Extra, ...] = ()
    period_label: str = "Mês"
    first_month: str = FIRST_MONTH
    last_month: str | None = None  # last month with data, when the API stopped being updated
    extra_display: tuple[tuple[str, str], ...] = ()  # (column, path) shown as is

    @property
    def feature_columns(self) -> tuple[str, ...]:
        columns = ["log_value", "value_vs_unit"]
        if self.category:
            columns.append("value_vs_category")
        if self.favored:
            columns += ["favored_log_count", "value_vs_favored", "favored_unit_count"]
        columns += [g.name for g in self.group_counts]
        columns += [e.name for e in self.extras]
        return tuple(columns)

    @property
    def display_columns(self) -> tuple[str, ...]:
        columns = ["date"]
        if self.favored:
            columns += ["favored_type", "favored_name"]
        columns.append("management_unit_name")
        if self.category:
            columns.append(self.category.column)
        columns += [column for column, _ in self.extra_display]
        columns += ["value", "portal_id"]
        return tuple(columns)


BASES: dict[str, PortalBase] = {base.name: base for base in (
    PortalBase(
        name="portal_payments",
        period_label="Mês do recebimento",
        label="Recebimentos de recursos por favorecido (API do Portal)",
        endpoint="/despesas/recursos-recebidos",
        agency_param="orgao",
        period=month_params("mesAnoInicio", "mesAnoFim"),
        dates=("anoMes",),
        values=("valor",),
        unit_code="codigoUG",
        unit_name="nomeUG",
        favored=Favored(("codigoPessoa",), "nomePessoa"),
        extra_display=(("uf", "siglaUFPessoa"),),
    ),
    PortalBase(
        name="portal_cards",
        period_label="Mês do extrato",
        label="Cartão de pagamento do governo (API do Portal)",
        endpoint="/cartoes",
        agency_param="codigoOrgao",
        period=month_params("mesExtratoInicio", "mesExtratoFim"),
        dates=("dataTransacao", "mesExtrato"),  # classified expenses come without the transaction date
        values=("valorTransacao",),
        unit_code="unidadeGestora.codigo",
        unit_name="unidadeGestora.nome",
        portal_id="id",
        category=Category("card_type", "tipoCartao.descricao"),
        favored=Favored(("estabelecimento.cnpjFormatado", "estabelecimento.cpfFormatado"), "estabelecimento.nome"),
        group_counts=(GroupCount("holder_log_count", ("portador.cpfFormatado",), "portador.nome"),),
        extras=(Extra("weekend", weekend),),
    ),
    PortalBase(
        name="portal_travel",
        period_label="Mês de início da viagem",
        label="Viagens a serviço (API do Portal)",
        endpoint="/viagens",
        agency_param="codigoOrgao",
        period=travel_params,
        dates=("dataInicioAfastamento",),
        values=("valorTotalViagem",),
        unit_code="unidadeGestoraResponsavel.codigo",
        unit_name="unidadeGestoraResponsavel.nome",
        portal_id="id",
        category=Category("travel_situation", "situacao"),
        favored=Favored(("beneficiario.cpfFormatado",), "beneficiario.nome", always_individual=True),
        extras=(
            Extra("log_duration_days", lambda item: days_between(item, "dataInicioAfastamento", "dataFimAfastamento")),
            Extra("daily_allowance_share", lambda item: share(item, "valorTotalDiarias", "valorTotalViagem")),
            Extra("ticket_share", lambda item: share(item, "valorTotalPassagem", "valorTotalViagem")),
        ),
    ),
    PortalBase(
        name="portal_contracts",
        period_label="Vigência no mês",
        label="Contratos (API do Portal)",
        endpoint="/contratos",
        agency_param="codigoOrgao",
        period=date_params("dataInicial", "dataFinal"),
        dates=("dataAssinatura", "dataInicioVigencia"),
        values=("valorFinalCompra", "valorInicialCompra"),
        unit_code="unidadeGestora.codigo",
        unit_name="unidadeGestora.nome",
        portal_id="id",
        category=Category("purchase_modality", "modalidadeCompra"),
        favored=Favored(("fornecedor.cnpjFormatado", "fornecedor.cpfFormatado"), "fornecedor.nome"),
        extras=(
            Extra("value_change", value_change),
            Extra("log_duration_days", lambda item: days_between(item, "dataInicioVigencia", "dataFimVigencia")),
        ),
    ),
    PortalBase(
        name="portal_biddings",
        period_label="Mês de abertura",
        last_month="2024-04",  # no biddings in the API after April 2024 (checked on 2026-10-27)
        label="Licitações (API do Portal)",
        endpoint="/licitacoes",
        agency_param="codigoOrgao",
        period=date_params("dataInicial", "dataFinal"),
        dates=("dataAbertura", "dataPublicacao"),
        values=("valor",),
        unit_code="unidadeGestora.codigo",
        unit_name="unidadeGestora.nome",
        portal_id="id",
        category=Category("bidding_modality", "modalidadeLicitacao"),
        extras=(Extra("log_days_to_result", lambda item: days_between(item, "dataAbertura", "dataResultadoCompra")),),
        extra_display=(("bidding_situation", "situacaoCompra"),),
    ),
    PortalBase(
        name="portal_agreements",
        period_label="Vigência no mês",
        label="Convênios e transferências (API do Portal)",
        endpoint="/convenios",
        agency_param="codigoOrgao",
        # dataInicial/dataFinal filter dataReferencia, the date of the last update of the record: use the validity.
        period=date_params("dataVigenciaInicial", "dataVigenciaFinal"),
        dates=("dataInicioVigencia", "dataPublicacao"),
        values=("valor",),
        unit_code="unidadeGestora.codigo",
        unit_name="unidadeGestora.nome",
        portal_id="id",
        category=Category("agreement_situation", "situacao"),
        favored=Favored(("convenente.cnpjFormatado", "convenente.cpfFormatado"), "convenente.nome"),
        extras=(
            Extra("released_share", lambda item: share(item, "valorLiberado", "valor")),
            Extra("counterpart_share", lambda item: share(item, "valorContrapartida", "valor")),
            Extra("log_duration_days", lambda item: days_between(item, "dataInicioVigencia", "dataFinalVigencia")),
        ),
    ),
)}


@dataclass
class FetchResult:
    items: list[dict[str, Any]]
    requests: int
    truncated: bool


def fetch(client: PortalClient, base: PortalBase, agency: str, first_month: str, last_month: str, max_rows: int,
          on_page: Callable[[str, int], None] | None = None) -> FetchResult:
    """Download the records of one agency, month by month, stopping once more than `max_rows` were received.

    The cut is truncated only when the Portal has records beyond the cap: reaching exactly `max_rows` costs one
    more request, to tell a complete cut from an interrupted one. Repeated records count toward the cap, since
    they are only removed by `normalize`.
    """
    items: list[dict[str, Any]] = []
    start = client.requests
    for month in months_between(first_month, last_month):
        for period in base.period(*month_bounds(month)):
            for page in client.pages(base.endpoint, {base.agency_param: agency, **period}):
                items.extend(page)
                if on_page:
                    on_page(month, min(len(items), max_rows))
                if len(items) > max_rows:
                    return FetchResult(items[:max_rows], client.requests - start, True)
    return FetchResult(items, client.requests - start, False)


def normalize(base: PortalBase, items: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, int]]:
    """One row per usable record, with the display values (already LGPD-safe) and the inputs of the features.

    Returns the rows and the count of records removed per reason (a record counts under its first reason).
    """
    rows, excluded, seen = [], {"duplicate": 0, "missing_date": 0, "non_positive_value": 0}, set()
    for item in items:
        portal_id = pick(item, base.portal_id) if base.portal_id else None
        if portal_id is not None:
            if portal_id in seen:
                excluded["duplicate"] += 1
                continue
            seen.add(portal_id)
        record_date = next((d for d in (parse_date(pick(item, p)) for p in base.dates) if d is not None), None)
        if record_date is None:
            excluded["missing_date"] += 1
            continue
        value = next((v for v in (parse_value(pick(item, p)) for p in base.values) if v is not None and v > 0), None)
        if value is None:
            excluded["non_positive_value"] += 1
            continue

        row: dict[str, Any] = {
            "date": record_date.isoformat(),
            "value": value,
            "portal_id": None if portal_id is None else str(portal_id),
            "management_unit_code": pick(item, base.unit_code),
            "management_unit_name": pick(item, base.unit_name),
        }
        if base.category:
            row[base.category.column] = pick(item, base.category.path)
        for column, path in base.extra_display:
            row[column] = pick(item, path)
        if base.favored:
            document = next((d for d in (pick(item, p) for p in base.favored.documents) if d), None)
            name = pick(item, base.favored.name)
            favored_type = classify_favored(document, base.favored.always_individual)
            row["favored_type"] = favored_type
            row["favored_name"] = name if favored_type in NAMED_TYPES else None
            row["favored_key"] = identity_hash(document, name, favored_type == "individual")
        for group in base.group_counts:
            document = next((d for d in (pick(item, p) for p in group.documents) if d), None)
            row[f"{group.name}_key"] = identity_hash(document, pick(item, group.person_name), True)
        for extra in base.extras:
            row[extra.name] = extra.compute(item)
        rows.append(row)
    return pd.DataFrame(rows), excluded


def compute_features(base: PortalBase, df: pd.DataFrame) -> pd.DataFrame:
    """Generic features relative to the cut (the API gives no history beyond it), plus the base extras."""
    f = pd.DataFrame(index=df.index)
    own = pd.Series("row:" + df.index.astype(str), index=df.index)  # records without identity stand alone
    log_value = np.log1p(df["value"].astype(float))
    f["log_value"] = log_value
    unit = df["management_unit_code"].fillna("")
    f["value_vs_unit"] = log_value - log_value.groupby(unit).transform("median")
    if base.category:
        category = df[base.category.column].fillna("")
        f["value_vs_category"] = log_value - log_value.groupby(category).transform("median")
    if base.favored:
        key = df["favored_key"].where(df["favored_key"].notna(), own)
        median = log_value.groupby(key).transform("median")
        mad = (log_value - median).abs().groupby(key).transform("median")
        f["favored_log_count"] = np.log1p(key.map(key.value_counts()))
        f["value_vs_favored"] = (log_value - median) / (mad + MAD_OFFSET)
        f["favored_unit_count"] = np.log1p(unit.groupby(key).transform("nunique"))
    for group in base.group_counts:
        key = df[f"{group.name}_key"].where(df[f"{group.name}_key"].notna(), own)
        f[group.name] = np.log1p(key.map(key.value_counts()))
    for extra in base.extras:
        values = pd.to_numeric(df[extra.name], errors="coerce").astype(float)
        median = values.median()
        f[extra.name] = values.fillna(0.0 if pd.isna(median) else median)
    return f[list(base.feature_columns)].astype(float)


def display_values(base: PortalBase, df: pd.DataFrame) -> Iterator[dict[str, Any]]:
    columns = list(base.display_columns)
    for record in df[columns].to_dict("records"):
        yield {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in record.items()}
