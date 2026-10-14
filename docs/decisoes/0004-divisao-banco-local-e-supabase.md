# 0004 — Divisão entre Postgres local e Supabase

- **Data:** 2026-10-14
- **Status:** aceita

## Contexto

O Supabase usado é do plano gratuito, com limite de 500 MB. A base de 2025 tratada (após as exclusões da decisão 0003) ocupa 1,33 GB no Postgres: `payments` 1.034 MB e `favored` 290 MB. Mesmo só com os dados tratados, a base não cabe.

## Decisão

| Banco | Conteúdo | Variável |
|---|---|---|
| **Postgres local** (Docker) | Base completa: `dataset_files`, `payments`, `favored`, `management_units`. Destino do ETL e origem das amostras. | `DATABASE_URL` |
| **Supabase** | Amostra estratificada do experimento, com os favorecidos e as unidades gestoras dela, e as tabelas de jobs, runs e resultados. É o banco lido pelo backend. | `SUPABASE_DATABASE_URL` |

## Consequências

- O ETL (`anomalygov_ml.ingest`) grava apenas no banco local.
- Será preciso um passo que sorteie a amostra no banco local e a copie para o Supabase. O critério e o tamanho da amostra ficam registrados na configuração do experimento.
- O modo `exploration` filtra apenas dentro da amostra que está no Supabase. A interface deve informar isso ao usuário.
- As medições de escalabilidade com amostras maiores rodam no banco local, e só os resultados vão para o Supabase.
- A base completa não fica disponível na aplicação publicada. Ela pode ser reconstruída a qualquer momento a partir dos CSVs brutos, conferidos pelos hashes em `docs/datasets.md`.

## Implementação (2026-10-14)

`python -m anomalygov_ml.publish <experimento>` copia do banco local (`DATABASE_URL`) para o Supabase (`SUPABASE_DATABASE_URL`), numa única transação e preservando os ids:

- a amostra principal com seus pagamentos, favorecidos e unidades gestoras, e os arquivos da base;
- os metadados de todas as amostras usadas pelas execuções (registros só da principal);
- todas as execuções do experimento, com `run_metrics` e `run_comparisons`;
- os escores por registro só das execuções principais (opção `--scores` para incluir outras finalidades).

Republicar é idempotente. As sequências de id do destino são ajustadas para que linhas criadas no próprio Supabase (por exemplo, execuções do modo `exploration`) não colidam com os ids publicados. Se um id de execução já pertencer a outro experimento no destino, a publicação é recusada.

Medido com `principal-2025` num banco local equivalente: **46 MB** no destino (`run_scores` 15 MB, `favored` 10 MB, `payments` 8,6 MB). As migrations precisam ser aplicadas no Supabase antes da primeira publicação.
