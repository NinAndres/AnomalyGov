# Contratos de integração

Documento de referência dos contratos entre backend (C#) e worker (Python). Toda alteração de schema exige nova migration em `db/migrations/` e atualização deste arquivo.

## Schema do banco

Migrations aplicadas em ordem numérica a partir de `db/migrations/`.

### `dataset_files` (001, 002)

Um registro por arquivo bruto ingerido. `sha256` é único: reingerir o mesmo arquivo é ignorado.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | integer | Identificador |
| `source` | text | Nome do adaptador (`payments`) |
| `file_name` | text | Nome do arquivo de origem |
| `sha256` | char(64) | Hash do arquivo bruto |
| `row_count` | integer | Linhas de dados do arquivo bruto (sem cabeçalho) |
| `loaded_row_count` | integer | Linhas gravadas em `payments` após as exclusões (002) |
| `excluded_rows` | jsonb | Linhas removidas por critério, ex.: `{"treasury_operation": 295, "negative_amount": 3919, "zero_amount": 5953}` (002) |
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

### `samples` e `sample_records` (003)

Amostras estratificadas (decisão 0005). Uma amostra é identificada pelo desenho: base, semente, total, piso, colunas de estrato e arquivos da base (`dataset_file_ids`). Reexecutar o mesmo desenho reaproveita a amostra gravada.

| Coluna | Tipo | Descrição |
|---|---|---|
| `samples.id` | integer | Identificador |
| `source` | text | Adaptador (`payments`) |
| `seed`, `total`, `floor` | integer | Semente, tamanho proporcional e piso por estrato |
| `strata` | text[] | Colunas de estrato (`reference_month`, `favored_type`) |
| `dataset_file_ids` | integer[] | Arquivos da base no momento do sorteio |
| `population_size`, `sample_size` | integer | Tamanho da população e da amostra |
| `sample_records.payment_id` | bigint | FK `payments` |
| `sample_records.weight` | double precision | Peso amostral (tamanho do estrato / sorteados) |

### `runs` (003)

Uma linha por execução de algoritmo (AGENTS.md, seção 7).

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | integer | Identificador |
| `experiment`, `config_sha256` | text, char(64) | Nome e hash do arquivo de configuração em `ml/experiments/configs/` |
| `mode` | text | `experiment` ou `exploration` |
| `purpose` | text | `main`, `parameter`, `data_stability`, `scalability` ou `artifact` (decisão 0006) |
| `algorithm` | text | `isolation_forest`, `lof` ou `one_class_svm` |
| `params` | jsonb | Hiperparâmetros completos efetivos (inclui `n_neighbors` derivado e `max_duplicate_group` no LOF) |
| `random_state` | integer | Semente do algoritmo (nula quando determinístico) |
| `feature_columns` | text[] | Features usadas, na ordem da matriz |
| `train_sample_id` | integer | Amostra de treino (FK `samples`) |
| `scored_sample_id` | integer | Amostra pontuada; nula na escalabilidade (só tempos) |
| `n_train`, `n_scored` | integer | Registros de treino e pontuados |
| `fit_seconds`, `score_seconds` | double precision | Tempos. No LOF sem `novelty`, a pontuação acontece no treino. |
| `environment` | jsonb | Versões de Python, scikit-learn, numpy, pandas, scipy, máquina e `n_jobs` |

### `run_scores` (003)

| Coluna | Tipo | Descrição |
|---|---|---|
| `run_id` | integer | FK `runs` |
| `payment_id` | bigint | FK `payments` |
| `raw_score` | double precision | Escore bruto (maior = mais anômalo) |
| `normalized_score` | real | Posto percentual em (0, 1]; sinalizado a `p` quando `raw_score` ≥ quantil `1 − p` da execução |

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
