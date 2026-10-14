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
