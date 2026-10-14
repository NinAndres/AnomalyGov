# Contratos de integração

Documento de referência dos contratos entre backend (C#) e worker (Python). Toda alteração de schema exige nova migration em `db/migrations/` e atualização deste arquivo.

## Schema do banco

Migrations aplicadas em ordem numérica a partir de `db/migrations/`.

### `dataset_files` (001)

Um registro por arquivo bruto ingerido. `sha256` é único: reingerir o mesmo arquivo é ignorado.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | integer | Identificador |
| `source` | text | Nome do adaptador (`payments`) |
| `file_name` | text | Nome do arquivo de origem |
| `sha256` | char(64) | Hash do arquivo bruto |
| `row_count` | integer | Linhas de dados (sem cabeçalho) |
| `period_start`, `period_end` | date | Primeiro e último dia do período coberto |
| `ingested_at` | timestamptz | Momento da ingestão |

### `management_units` (001)

Dimensão de unidades gestoras pagadoras, com órgão e órgão superior. É atualizada (upsert) a cada ingestão com os nomes mais recentes.

| Coluna | Tipo |
|---|---|
| `code` | varchar(6), PK |
| `name` | text |
| `agency_code`, `agency_name` | varchar(5), text |
| `superior_agency_code`, `superior_agency_name` | varchar(5), text |

### `favored` (001)

Dimensão de favorecidos.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | bigint | Identificador usado nas features |
| `key_hash` | bytea (32 bytes) | SHA-256 da identidade; ver decisão 0002 |
| `favored_type` | text | `individual`, `company`, `management_unit`, `foreign`, `special`, `other` |
| `code`, `name` | text | Nulos para `individual` |

### `payments` (001)

Fato: total recebido no mês por favorecido, unidade gestora e localidade.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | bigint | Identificador do registro (referenciado pelos resultados) |
| `dataset_file_id` | integer | FK `dataset_files` |
| `reference_month` | date | Primeiro dia do mês |
| `favored_id` | bigint | FK `favored` |
| `management_unit_code` | varchar(6) | FK `management_units` |
| `uf` | char(2) | `NULL` se sem informação; `EX` para exterior |
| `municipality` | text | `NULL` se sem informação |
| `amount` | numeric(18,2) | Valor recebido (pode ser negativo) |

## Filtros disponíveis por base

Definidos em `PaymentsAdapter.filters` (`ml/src/anomalygov_ml/sources/payments.py`):

| `name` | `type` | Rótulo |
|---|---|---|
| `reference_month` | `month_range` | Mês de referência |
| `superior_agency_code` | `select` | Órgão superior |
| `management_unit_code` | `select` | Unidade gestora |
| `uf` | `select` | UF |
| `favored_type` | `select` | Tipo de favorecido |
| `amount` | `number_range` | Valor recebido (R$) |

## Formato de `filters` e `params` dos jobs

_A definir._

## Formato dos resultados

_A definir._
