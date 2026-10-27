# 0014 — Bases consultadas na API do Portal da Transparência

- **Data:** 2026-10-27
- **Status:** aceita

## Contexto

O item 4 da prioridade do AGENTS.md pede um segundo tipo de base e um conector via API do Portal. Ele é uma extensão: o artigo não depende disso, e os resultados do modo `exploration` não entram no artigo (AGENTS.md, seção 10).

Cada base do Portal tem endpoint, parâmetros e formato de resposta próprios. Mesmo assim, quase todas compartilham os mesmos campos centrais: data, valor, unidade gestora e, em geral, um favorecido (fornecedor, portador, viajante, convenente).

Os endpoints, os parâmetros obrigatórios e os campos de resposta foram levantados na especificação OpenAPI pública da API (`https://api.portaldatransparencia.gov.br/v3/api-docs`, consultada em 2026-10-26).

## Decisões

- **Adaptador genérico guiado por declaração.** Cada base é um `PortalBase` em `ml/src/anomalygov_ml/portal/bases.py`. Ele declara o endpoint, como montar os parâmetros de um mês e onde estão os campos centrais no JSON. Também pode declarar features extras. A normalização, o tratamento LGPD e as features genéricas são compartilhados por todas as bases. Uma base nova é uma declaração nova.
- **Seis bases.** Todas permitem recortar por órgão e período:

  | Base (`sources.name`) | Endpoint | Data | Valor | Favorecido | Categoria | Features extras |
  |---|---|---|---|---|---|---|
  | `portal_payments` | `/despesas/recursos-recebidos` | mês do recebimento | `valor` | favorecido | — | — |
  | `portal_cards` | `/cartoes` | data da transação | `valorTransacao` | estabelecimento | tipo de cartão | `weekend`, `holder_log_count` (frequência do portador, só como hash) |
  | `portal_travel` | `/viagens` | início do afastamento | `valorTotalViagem` | viajante (sempre pessoa física) | situação | `log_duration_days`, `daily_allowance_share`, `ticket_share` |
  | `portal_contracts` | `/contratos` | assinatura | `valorFinalCompra` (ou o inicial) | fornecedor | modalidade da compra | `value_change` (ln do final sobre o inicial), `log_duration_days` |
  | `portal_biddings` | `/licitacoes` | abertura | `valor` | — | modalidade | `log_days_to_result` |
  | `portal_agreements` | `/convenios` | referência | `valor` | convenente | situação | `released_share`, `counterpart_share`, `log_duration_days` |

  `portal_payments` é a mesma base do experimento (decisão 0001), consultada pela API. Ela permite explorar outros períodos, como 2024 ou 2026, sem ingerir CSVs.
- **Recorte via job.** O usuário escolhe a base, **um** órgão (código SIAFI) e um período de **até 12 meses**. Os dois filtros são obrigatórios. O worker consulta a API mês a mês, normaliza os registros, calcula as features e roda os três algoritmos com a configuração principal do experimento (decisão 0006), como nos recortes da amostra (decisão 0010).
- **Features relativas ao recorte.** A API não dá o histórico além do recorte, então as features genéricas são calculadas dentro dele:
  - `log_value`;
  - `value_vs_unit` e `value_vs_category`: o valor em log menos a mediana da unidade gestora ou da categoria;
  - quando há favorecido: `favored_log_count`, `value_vs_favored` (z-score robusto, como na decisão 0005) e `favored_unit_count`.

  Os valores ausentes de uma feature extra são imputados com a mediana do recorte.
- **Exclusões:** registros repetidos (mesmo id do Portal, comum em contratos vigentes em mais de um mês consultado), sem data e sem valor positivo. As contagens ficam no resultado do job.
- **Teto de registros.** `EXPLORATION_PORTAL_MAX_ROWS` vale 10.000 por padrão. A API não informa o total antes da consulta, então o download é interrompido no teto e o job registra `truncated`. Nesse caso, o recorte analisado contém os primeiros registros devolvidos pelo Portal, e **não** uma amostra aleatória. A interface avisa isso.
- **Cliente da API** (`portal/client.py`, só com a biblioteca padrão):
  - a chave vai apenas no header `chave-api-dados`, lida de `PORTAL_API_KEY`, e nunca aparece em logs, mensagens ou `repr`;
  - as requisições são espaçadas para ficar abaixo do limite do Portal (`PORTAL_API_REQUESTS_PER_MINUTE`, padrão 80, abaixo do limite diurno de 90 por minuto);
  - erros 429, 5xx e falhas de rede são repetidos com espera crescente (2, 4, 8, 16 e 32 s, respeitando `Retry-After`);
  - 401 e 403 não são repetidos;
  - o endpoint restrito `/despesas/documentos-por-favorecido` não é usado.
- **LGPD.** O nome do favorecido só é gravado para pessoa jurídica e unidade gestora. Pessoa física e favorecidos não identificados aparecem ocultos. Portadores de cartão e viajantes nunca têm nome ou CPF gravados: servem só como hash em memória, para as contagens.
- **Armazenamento** (migration 009): os registros baixados ficam em `portal_records` e os escores em `portal_scores` (`run_scores` referencia `payments`). Os dois são apagados com o job, pela retenção de 24 h. As execuções dessas bases têm `train_sample_id` nulo.
- **Registro das bases:** `python -m anomalygov_ml.portal.register` grava as definições em `sources` com `kind = 'portal'`. As opções de órgão são os órgãos das unidades gestoras do banco local, que pagaram algo nos dados ingeridos (263 em 2025). O mês final disponível é o mês em que o comando foi executado, e rodá-lo de novo atualiza esse limite.

## Consequências

- Um job de uma base do Portal leva minutos, não segundos. Com cerca de 15 registros por página e 80 requisições por minuto, o teto de 10.000 registros leva cerca de 8 minutos. Enquanto isso, o worker não processa outros jobs. O job informa o andamento (`jobs.progress`), e o frontend o exibe.
- O tamanho da página não é documentado. O cliente considera como última a página vazia ou a página menor que a maior já recebida.
- **Não testado contra a API real:** a chave não estava configurada quando a extensão foi implementada. Os formatos de data e valor seguem a especificação OpenAPI, e o código aceita as variações comuns (ISO, DD/MM/AAAA, "1.234,56"). Também não foi verificado se os endpoints aceitam os intervalos usados (um mês por requisição; em viagens, retorno até o fim do mês seguinte). A primeira execução com a chave deve conferir isso.
- Viagens com retorno depois do fim do mês seguinte ao início ficam fora do recorte.
- As features das bases do Portal não são comparáveis com as do experimento: lá elas usam o ano inteiro (decisão 0005), aqui só o recorte.
