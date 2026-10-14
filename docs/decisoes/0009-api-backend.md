# 0009 — API do backend

- **Data:** 2026-10-14
- **Status:** aceita

## Contexto

O item 3 da prioridade do AGENTS.md pede uma API em C# que orquestre jobs e exponha resultados, sem executar algoritmos e sem chamar o Python (seção 4.2). O banco de produção é o Supabase do plano gratuito (decisão 0004), com RLS em todas as tabelas (migration 005).

## Decisões

- **ASP.NET Core 9, Minimal API**, em `backend/AnomalyGov.Api`; testes xUnit em `backend/AnomalyGov.Api.Tests` (`cd backend && dotnet test`).
- **Npgsql + Dapper** para acesso a dados. O schema é definido pelas migrations SQL de `db/`, que são o contrato com o worker. Um ORM com migrations próprias duplicaria esse contrato.
- **O backend é genérico em relação à base:** filtros, opções e colunas de exibição vêm da tabela `sources`, gravada pelo Python a partir do adaptador. Os registros são lidos da view `<source>_display`. Uma base nova não exige mudança no backend.
- **Regra de sinalização reproduzida em SQL** (`percentile_cont`), validada por teste contra os `flagged_count` calculados em Python.
- **Jobs identificados por UUID**, para não serem enumeráveis.
- **Conexão:** `ConnectionStrings:Default` ou a variável `SUPABASE_DATABASE_URL` (URL libpq, convertida para o formato do Npgsql). O papel usado ignora o RLS, que continua bloqueando a API REST do Supabase.
- **Sem autenticação** nesta etapa. Como cada job consome tempo do worker, `POST /api/jobs` é limitado por IP (10 por minuto, configurável).
- **CORS** liberado só para as origens configuradas (`Cors:AllowedOrigins`; em desenvolvimento, `http://localhost:5173`).
- **Textos de erro em português**, no formato Problem Details.

## Consequências

- O worker Python (próximo passo) precisa seguir o processamento descrito em `docs/contratos.md`: reserva com `FOR UPDATE SKIP LOCKED`, execuções com `job_id` e `result` no formato documentado.
- A interface não pode depender de detalhes internos dos algoritmos (seção 9 do AGENTS.md): ela recebe escores normalizados e sinalizações, não escores brutos.
- Antes de publicar a aplicação, é preciso decidir sobre autenticação. Sem ela, qualquer pessoa com acesso à URL pode criar jobs, dentro do limite por IP.
