# AnomalyGov

Avaliação comparativa de algoritmos de detecção de anomalias não supervisionados (Isolation Forest, LOF e One-Class SVM) em pagamentos a favorecidos do Poder Executivo Federal (Portal da Transparência, 2025). TCC II — Engenharia de Software, UniAmérica.

Registros sinalizados são **estatisticamente atípicos** e não indicam fraude, irregularidade ou ilegalidade.

- Regras do projeto: [`AGENTS.md`](AGENTS.md)
- Decisões técnicas e metodológicas: [`docs/decisoes/`](docs/decisoes/)
- Contratos (banco, jobs, API): [`docs/contratos.md`](docs/contratos.md)
- Bases e exclusões: [`docs/datasets.md`](docs/datasets.md)
- Resultados do experimento: [`docs/resultados/principal-2025.md`](docs/resultados/principal-2025.md)
- Figuras do artigo: geradas localmente em `docs/resultados/figuras/principal-2025/` (não versionadas; ver decisão 0013)

## Arquitetura

```
ETL e experimento (Python) → Postgres local (base completa, 8,1 milhões de registros)
                                   │ publicação (amostra, features, resultados)
                                   ▼
React → API C# → Supabase (jobs, resultados) ← worker Python
```

- **`ml/`** — ETL, features, amostragem, algoritmos, métricas, hipóteses, publicação e worker.
- **`backend/`** — API ASP.NET Core 9: bases, jobs e resultados. Não executa algoritmos.
- **`frontend/`** — React + TypeScript (Vite): resultados do experimento e exploração por recorte.
- **`db/migrations/`** — schema; aplicar em ordem no Postgres local e no Supabase.

## Pré-requisitos

- Python 3.11+ (testado com 3.14), .NET SDK 9, Node 20.18+, Docker.
- **O caminho do projeto não pode conter `#`**: o Vite e o Vitest não funcionam nesse caso (decisão 0011).
- Arquivo `.env` na raiz, a partir do [`.env.example`](.env.example). Ele nunca é versionado.
- No `SUPABASE_DATABASE_URL`, usar a connection string do **Session Pooler** (IPv4), e não a conexão direta, que só tem IPv6 (nota na decisão 0010).

## Banco local (Docker)

```bash
docker run -d --name anomalygov-pg -e POSTGRES_PASSWORD=postgres -p 15432:5432 postgres:17
for f in db/migrations/0*.sql; do docker exec -i anomalygov-pg psql -U postgres -v ON_ERROR_STOP=1 -q < "$f"; done
```

A porta 15432 foi escolhida porque a faixa 55318–55817 é reservada pelo Windows. Os dados ficam no volume do container: `docker stop`/`start` preservam a base, `docker rm` apaga (a reingestão leva ~18 min).

## Pipeline de dados e experimento (`ml/`)

```bash
cd ml
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
set -a && . ../.env && set +a   # DATABASE_URL e SUPABASE_DATABASE_URL

# 1. ETL: CSVs mensais "Recebimentos de Recursos por Favorecido" em data/raw/
.venv/Scripts/python -m anomalygov_ml.ingest ../data/raw/2025*_RecebimentosRecursosPorFavorecido.csv
# 2. Experimento (~50 min) e hipóteses (~10 min)
.venv/Scripts/python -m anomalygov_ml.experiment experiments/configs/principal-2025.toml
.venv/Scripts/python -m anomalygov_ml.hypotheses experiments/configs/principal-2025-hipoteses.toml
# 3. Métricas e relatório
.venv/Scripts/python -m anomalygov_ml.report principal-2025 --out ../docs/resultados/principal-2025.md
# Figuras do artigo (PNG 300 dpi e SVG), a partir das tabelas gravadas pelo relatório
.venv/Scripts/python -m anomalygov_ml.figures principal-2025
# 4. Publicação no Supabase (migrations aplicadas antes)
.venv/Scripts/python -m anomalygov_ml.publish principal-2025
```

## Aplicação

Três processos, com o `.env` carregado:

```bash
# API (http://localhost:5183)
ASPNETCORE_ENVIRONMENT=Development dotnet run --project backend/AnomalyGov.Api --launch-profile http
# Worker do modo exploração
cd ml && .venv/Scripts/python -m anomalygov_ml.worker --config experiments/configs/principal-2025.toml
# Frontend (http://localhost:5173, repassa /api para a API)
cd frontend && npm install && npm run dev
```

## Testes

| Módulo | Comando | Integração |
|---|---|---|
| ML | `cd ml && .venv/Scripts/python -m pytest` | com `DATABASE_URL` apontando para o banco local |
| Backend | `cd backend && dotnet test` | com `ANOMALYGOV_TEST_DATABASE_URL` apontando para um banco com o experimento publicado (ex.: `anomalygov_supabase_local`) |
| Frontend | `cd frontend && npm test` | API simulada |

Sem as variáveis, os testes de integração são pulados.

## Pendências conhecidas

- **Autenticação:** a API não tem login. A criação de jobs é limitada por IP (decisão 0009). Decidir antes de publicar a aplicação.