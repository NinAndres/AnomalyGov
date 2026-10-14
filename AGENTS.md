# AGENTS.md — AnomalyGov

## 1. Contexto do projeto

O AnomalyGov é um projeto acadêmico (TCC II — Engenharia de Software, UniAmérica) para avaliar comparativamente algoritmos de detecção de anomalias não supervisionados aplicados a registros públicos de pagamentos a favorecidos do Poder Executivo Federal brasileiro.

O projeto utiliza dados públicos do Portal da Transparência e busca identificar registros estatisticamente atípicos. Uma anomalia detectada não deve ser interpretada automaticamente como fraude, irregularidade ou ilegalidade.

### 1.1 Escopo e prazo

- **Período dos dados do experimento:** janeiro a dezembro de 2025.
- **Entrega final do artigo:** 20/11/2026.
- **Prioridade de implementação** (nesta ordem; um item só começa quando o anterior produz resultado utilizável):
  1. ETL dos CSVs de pagamentos de 2025 para o banco.
  2. Execução em lote dos três algoritmos e cálculo das métricas da seção 2.
  3. API em C# com orquestração por jobs e frontend exibindo resultados.
  4. Segundo tipo de base e conector via API do Portal (extensão; o artigo não depende disso).

## 2. Objetivo científico

Comparar os seguintes algoritmos:

- Isolation Forest
- Local Outlier Factor (LOF)
- One-Class SVM

A avaliação deve considerar, conforme definido na metodologia:

- Tempo de execução.
- Proporção de registros classificados como anômalos.
- Estabilidade diante de alterações nos parâmetros e nos dados.
- Concordância e divergência entre os algoritmos.
- Características estatísticas dos registros sinalizados.
- Interpretabilidade dos resultados.

Não utilizar acurácia, precisão, recall ou F1-score como métricas de desempenho preditivo sem rótulos de referência confiáveis.

Hipóteses do trabalho (devem ser testadas, não assumidas):

- **H1:** a distribuição atípica dos registros impacta significativamente o desempenho comparativo dos algoritmos.
- **H2:** o Isolation Forest apresenta maior estabilidade que o LOF em registros estruturalmente não estacionários.

### 2.1 Definição operacional de anomalia

- Cada algoritmo produz um escore contínuo, normalizado para que **valores maiores signifiquem registros mais anômalos**.
- Um registro é sinalizado como anômalo quando seu escore está entre os `p%` maiores do respectivo algoritmo (limiar percentual, conforme a metodologia).
- O mesmo `p` é aplicado aos três algoritmos em uma mesma execução, para que a comparação seja justa.

## 3. Tecnologias

- Machine Learning e ETL: Python, Pandas, NumPy e scikit-learn.
- Backend (orquestrador): C# e .NET 9.
- Frontend: React e TypeScript.
- Banco de dados: PostgreSQL com Supabase.
- Controle de versão: Git.

Antes de adicionar dependências ou tecnologias, verificar se já existe uma solução adequada no projeto.

## 4. Arquitetura

### 4.1 Responsabilidades dos módulos

| Módulo | Responsabilidade |
|---|---|
| `ml/` (Python) | Ingestão (CSV ou API do Portal), ETL, extração de features, execução dos algoritmos, métricas e gravação dos resultados. Roda como **worker**. |
| `backend/` (C#) | Orquestração: recebe filtros do frontend, cria jobs, acompanha status, expõe resultados. Não executa algoritmos. |
| `frontend/` (React) | Interface: seleção de base e filtros, acompanhamento do job, visualização dos resultados. |
| `db/` | Schema e migrations do PostgreSQL. É o contrato de integração entre backend e worker. |

### 4.2 Fluxo de execução

```
React → API C# → tabela jobs (Postgres) ← worker Python → tabelas de resultados (Postgres) → API C# → React
```

- O backend insere um job com status `pending`.
- O worker reserva o job com `SELECT ... FOR UPDATE SKIP LOCKED`, muda para `running`, processa e grava `succeeded` ou `failed` (com mensagem de erro).
- O frontend consulta o status do job até a conclusão (polling).
- O backend **nunca** chama o Python diretamente (sem subprocesso, sem HTTP entre os dois).

### 4.3 Adaptadores de fonte de dados

Cada tipo de base do Portal (pagamentos, e futuramente outros) é implementado como um adaptador em `ml/src/anomalygov_ml/sources/`, seguindo a interface `SourceAdapter`. Um adaptador define:

- **Ingestão:** como ler a origem (CSV em lote ou endpoint da API) e gravar no banco.
- **Filtros disponíveis:** lista declarativa (nome, tipo, rótulo). O backend lê essa definição e o frontend monta a tela de filtros a partir dela.
- **Features:** como transformar registros em matriz numérica.
- **Colunas de exibição:** quais atributos mostrar junto aos resultados.

Os algoritmos (`ml/src/anomalygov_ml/models/`) são agnósticos à base: recebem apenas a matriz de features. Não colocar lógica específica de uma base dentro dos algoritmos.

### 4.4 Modos de execução

- **`experiment`** — experimento científico. Lote sobre a base de pagamentos de 2025, com parâmetros fixos, sementes registradas e variações de hiperparâmetros definidas em `ml/experiments/configs/`. **É a única fonte dos resultados apresentados no artigo.**
- **`exploration`** — exploração interativa pela aplicação. Usuário filtra, o sistema roda os três algoritmos sob demanda. As anomalias são relativas ao recorte filtrado, e a interface deve deixar isso explícito.

## 5. Dados e segurança

- Nunca versionar credenciais, tokens, senhas ou arquivos `.env` reais.
- Utilizar `.env.example` com nomes de variáveis e valores fictícios.
- Não versionar bases brutas. CSVs brutos ficam em `data/raw/` (ignorado pelo Git) ou em storage externo.
- Registrar o hash SHA-256, o número de linhas e o período de cada arquivo ingerido (tabela `dataset_files`).
- Preservar a origem, o período de referência e a rastreabilidade dos dados.
- Documentar transformações, exclusões, valores ausentes e critérios de seleção em `docs/datasets.md`.
- Não modificar os dados de origem sem manter uma forma de reproduzir o processamento.
- Gravar no banco apenas as colunas necessárias à análise e à exibição (limite de armazenamento do Supabase).

### 5.1 API do Portal da Transparência

- A chave é enviada no header `chave-api-dados` e lida exclusivamente da variável de ambiente `PORTAL_API_KEY`.
- Nunca registrar a chave em logs.
- Respeitar os limites de requisições do Portal com controle de taxa no cliente. O endpoint `/despesas/documentos-por-favorecido` é restrito e tem limite menor. Ultrapassar os limites suspende o token.
- Implementar novas tentativas com espera crescente (backoff) para erros 429 e 5xx.
- Para volumes anuais, preferir o download em lote (CSV). A API é para recortes específicos.

### 5.2 LGPD

- Favorecidos podem ser pessoas físicas. CPFs e nomes de pessoas físicas não devem ser exibidos no frontend.
- Usar hash do documento do favorecido como identificador para cálculo de features (ex.: frequência de pagamentos por favorecido).
- Manter dados identificáveis apenas quando estritamente necessários e documentar o motivo.

## 6. Escalabilidade e amostragem

- O volume esperado é de aproximadamente 4 milhões de registros por ano.
- One-Class SVM não é viável na base completa, e o LOF tem custo elevado. Nos experimentos comparativos, usar **amostra estratificada**, com tamanho e critério de estratificação documentados na configuração do experimento.
- **A mesma amostra deve ser aplicada aos três algoritmos** em uma mesma execução comparativa.
- O tempo de execução de cada algoritmo em diferentes tamanhos de amostra é um resultado do experimento (escalabilidade) e deve ser registrado.
- No modo `exploration`, aplicar um teto de registros (`EXPLORATION_MAX_ROWS`). Se o filtro exceder o teto, amostrar e informar o usuário.

## 7. Reprodutibilidade

Cada execução de algoritmo (tabela `runs`) deve registrar:

- Dataset e arquivos usados (com hashes).
- Filtros aplicados e critério de amostragem.
- Hiperparâmetros completos e `random_state`.
- Limiar percentual `p`.
- Versões de Python, scikit-learn, pandas e numpy.
- Tempo de execução e número de registros processados.

Configurações de experimentos ficam versionadas em `ml/experiments/configs/`.

## 8. Testes e validação

- Criar ou atualizar testes para mudanças relevantes.
- Validar o pré-processamento com casos conhecidos e dados ausentes.
- Verificar se cada algoritmo produz resultados no formato esperado.
- Garantir que os experimentos possam ser reproduzidos com parâmetros documentados.
- Executar os testes pertinentes antes de considerar uma tarefa concluída.
- Informar quais testes foram executados e quais não puderam ser executados.

Comandos:

| Módulo | Comando |
|---|---|
| ML | `cd ml && python -m pytest` |
| Backend | `cd backend && dotnet test` |
| Frontend | `cd frontend && npm test` |

## 9. Integração entre módulos

- Os contratos de integração (schema do banco, formato de `filters` e `params` dos jobs, formato dos resultados) estão documentados em `docs/contratos.md`.
- Alterações no schema exigem nova migration em `db/migrations/` e atualização de `docs/contratos.md`.
- Não acoplar a interface a detalhes internos dos algoritmos.

## 10. Resultados científicos

- Não afirmar que um algoritmo é superior sem evidências experimentais.
- Registrar os parâmetros, a versão dos dados e as condições de execução de cada experimento.
- Distinguir resultados observados, hipóteses e interpretações.
- Não apresentar registros sinalizados como casos comprovados de fraude.
- Preservar resultados suficientes para comparar os algoritmos de forma consistente.
- Resultados do modo `exploration` não entram no artigo.

## 11. Convenções

- Código (variáveis, funções, classes, tabelas): inglês.
- Documentação, mensagens de commit e textos da interface: português.
- Decisões técnicas e metodológicas relevantes: registrar em `docs/decisoes/` (um arquivo por decisão, numerado).

## 12. Fluxo de trabalho

Antes de implementar uma tarefa:

1. Inspecionar os arquivos e padrões existentes.
2. Identificar os módulos afetados.
3. Propor uma alteração compatível com a arquitetura atual.
4. Implementar a solução com o menor escopo necessário.
5. Executar testes e validações pertinentes.
6. Atualizar a documentação quando necessário.
7. Resumir as alterações, os testes realizados e eventuais limitações.