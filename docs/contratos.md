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

### `run_metrics` e `run_comparisons` (004)

Calculadas por `python -m anomalygov_ml.report <experimento>` (decisão 0007) para as execuções que pontuaram a amostra principal. Reprocessar substitui as linhas das mesmas execuções.

| Coluna | Tipo | Descrição |
|---|---|---|
| `run_metrics.run_id`, `p` | integer, numeric(4,3) | Execução e limiar |
| `flagged_count` | integer | Registros sinalizados (com empates no limiar) |
| `flagged_share` | double precision | Proporção na amostra |
| `weighted_flagged_share` | double precision | Proporção ponderada pelos pesos amostrais (estimativa populacional) |
| `run_comparisons.run_a`, `run_b`, `p` | integer, integer, numeric(4,3) | Par de execuções (`run_a < run_b`) e limiar |
| `jaccard` | double precision | Jaccard dos sinalizados no limiar `p` |
| `spearman` | double precision | Correlação de Spearman dos escores (não depende de `p`) |

### Hipóteses (005)

`runs` ganha a coluna `subset` (jsonb, nula = amostra inteira) e as finalidades `h1_cell`, `h1_subsample`, `h1_manipulation`, `h2_month` e `h2_noise` (decisão 0008).

| Tabela | Colunas principais |
|---|---|
| `hypothesis_units` | `experiment`, `hypothesis` (`H1`, `H2`), `unit` (jsonb: célula, par de meses ou fração de manipulação), `measures` (jsonb: indicadores da unidade) |
| `hypothesis_tests` | `experiment`, `hypothesis`, `family` (família da correção de Holm), `test`, `variable`, `n`, `statistic`, `effect`, `ci_low`, `ci_high`, `p_value`, `p_adjusted`, `details` (jsonb, inclui `alpha`) |

### Segurança (005)

Todas as tabelas têm RLS ativo e nenhuma política. No Supabase, isso bloqueia o acesso pela API REST (papéis `anon` e `authenticated`). O backend deve conectar com um papel que ignore RLS (o dono das tabelas ou `postgres`). Expor dados pela API exigirá políticas explícitas numa migration nova.

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

### `sources`, `jobs` e `payments_display` (006)

| Objeto | Descrição |
|---|---|
| `sources` | Uma linha por base: `name`, `label`, `filters` (jsonb: `[{name, type, label, options?, min?, max?}]`) e `display_columns` (jsonb). Gravada pela publicação (`anomalygov_ml.publish`), com as opções e faixas calculadas a partir da amostra publicada. |
| `jobs` | Fila do modo `exploration`: `id` (uuid), `source`, `status` (`pending` → `running` → `succeeded` ou `failed`), `filters`, `params`, `result`, `error`, `created_at`, `started_at`, `finished_at`. Restrições garantem a coerência entre `status`, datas e `error`. |
| `runs.job_id` | Liga as execuções de um job (nulo no modo `experiment`). Apagar o job apaga suas execuções e escores. |
| `payments_display` | View com as colunas de exibição de cada pagamento (`<source>_display` é a convenção lida pelo backend). Nome e código de pessoa física são sempre nulos. `security_invoker = true`: respeita o RLS de quem consulta. |

### `record_features` e `sources.feature_columns` (007)

| Objeto | Descrição |
|---|---|
| `record_features` | `source`, `record_id`, `values` (float8[] na ordem de `sources.feature_columns`). Features dos registros da amostra publicada, calculadas no banco local sobre o ano inteiro (decisão 0005) e gravadas pela publicação, que substitui as anteriores da mesma base. |
| `sources.feature_columns` | Nomes das features, na ordem de `record_features.values`. |

## Formato de `filters` e `params` dos jobs

Validados pelo backend contra a definição em `sources` (`JobRequestValidator`). Todos os filtros são opcionais; filtros desconhecidos são rejeitados.

| Tipo de filtro | Formato | Regras |
|---|---|---|
| `month_range` | `{"from": "2025-03", "to": "2025-06"}` | `AAAA-MM`; ao menos um dos limites; `from` ≤ `to`; o intervalo precisa tocar a faixa `min`–`max` disponível |
| `select` | `["26000", "36000"]` | Lista não vazia de textos (até 500), todos presentes em `options` |
| `number_range` | `{"min": 100, "max": 5000}` | Ao menos um dos limites; `min` ≤ `max` |

Exemplo (base `payments`):

```json
{
  "source": "payments",
  "filters": {
    "reference_month": {"from": "2025-01", "to": "2025-06"},
    "favored_type": ["company"],
    "amount": {"min": 1000}
  },
  "params": {"p": 0.01}
}
```

`params` aceita apenas `p` (0 < p ≤ 0,10; padrão 0,01). Os algoritmos usam a configuração principal do experimento publicado (decisão 0006); o usuário não escolhe hiperparâmetros.

## Processamento de um job (worker)

Implementado em `ml/src/anomalygov_ml/worker.py` (decisão 0010): `python -m anomalygov_ml.worker --config experiments/configs/principal-2025.toml`, conectado a `SUPABASE_DATABASE_URL`.

1. **Limpeza**, a cada ciclo: jobs em `running` há mais de `EXPLORATION_STALE_MINUTES` (padrão 30) viram `failed` ("processamento interrompido"). Jobs concluídos há mais de `EXPLORATION_RETENTION_HOURS` (padrão 24) são apagados, junto com suas execuções e escores.
2. **Reserva:** `SELECT ... FROM jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED`, depois `status = 'running'` e `started_at = now()`.
3. **Recorte:** registros de `<source>_display` que atendem aos filtros e têm features em `record_features`. Cada filtro corresponde à coluna de mesmo nome da view. Com menos de `EXPLORATION_MIN_ROWS` (padrão 100), o job falha com uma mensagem para o usuário. Com mais de `EXPLORATION_MAX_ROWS` (padrão 50.000), sorteia esse número com semente derivada do id do job.
4. **Execução:** os três algoritmos com a configuração principal do experimento (`--config`), sobre as features do recorte com `RobustScaler` ajustado no próprio recorte. As anomalias são **relativas ao recorte**.
5. **Gravação, numa única transação:** uma linha em `runs` por algoritmo (`mode = 'exploration'`, `purpose = 'main'`, `experiment = 'exploration'`, `job_id`, `train_sample_id` e `scored_sample_id` = amostra principal publicada, `subset` = `{filters, sampled, sample_seed}`), os escores em `run_scores`, e o job com `status = 'succeeded'`, `finished_at` e `result`. Em erro, nada é gravado e o job fica `failed` com uma mensagem sem detalhes internos.

`result` (jsonb):

```json
{
  "n_filtered": 12840,
  "n_used": 12840,
  "sampled": false,
  "sample_seed": null,
  "runs": {"isolation_forest": 801, "lof": 802, "one_class_svm": 803}
}
```

## API (backend)

Base `/api`, JSON em camelCase, erros no formato Problem Details (RFC 9457) com títulos em português. Projeto em `backend/AnomalyGov.Api`.

| Método e rota | Descrição |
|---|---|
| `GET /api/health` | Verifica a conexão com o banco |
| `GET /api/sources`, `GET /api/sources/{name}` | Definição das bases (filtros com opções, colunas de exibição) |
| `POST /api/jobs` | Cria um job `pending` (201 + `Location`); 400 com `errors` por campo (`filters.<nome>`, `params.p`); limitado por IP (`RateLimiting:JobsPerMinute`, padrão 10/min) |
| `GET /api/jobs/{id}` | Estado do job (o frontend consulta até concluir) |
| `GET /api/jobs/{id}/records?algorithm=&page=&pageSize=` | Registros sinalizados do job (409 se o job não terminou com sucesso) |
| `GET /api/experiments` | Experimentos publicados |
| `GET /api/experiments/{name}` | Execuções principais com métricas, concordância, estabilidade, escalabilidade e testes de hipóteses |
| `GET /api/experiments/{name}/records?p=&algorithm=&page=&pageSize=` | Registros sinalizados pelas execuções principais |

## Formato dos resultados

Os registros sinalizados (`/records`) seguem a regra da decisão 0006: sinalizado quando `raw_score` ≥ quantil `1 − p` dos escores da execução, com interpolação linear (`percentile_cont`, igual ao `numpy.quantile`). A lista traz os registros sinalizados por **ao menos um** algoritmo, ordenados pelo número de algoritmos que os sinalizaram e pelo maior escore. `algorithm` restringe aos sinalizados por um algoritmo. `pageSize` vai até 200.

```json
{
  "p": 0.01, "algorithm": null, "page": 1, "pageSize": 50, "total": 1255,
  "items": [{
    "paymentId": 3672062,
    "flaggedCount": 3,
    "flags": {"isolation_forest": true, "lof": true, "one_class_svm": true},
    "scores": {"isolation_forest": 0.9986, "lof": 0.9998, "one_class_svm": 1.0},
    "values": {"reference_month": "2025-07", "favored_type": "management_unit", "favored_name": "...",
               "superior_agency_name": "...", "management_unit_name": "...", "uf": "DF",
               "municipality": "BRASÍLIA", "amount": 13668.91}
  }]
}
```

`scores` são os escores normalizados (posto percentual em (0, 1]). `values` traz as `display_columns` da base com os nomes de coluna originais. Valores não finitos (NaN, infinito) são devolvidos como `null`.
