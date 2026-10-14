# Bases de dados

Registro de origem, período, transformações, exclusões, valores ausentes e critérios de seleção de cada base utilizada.

## Recebimentos de Recursos por Favorecido (adaptador `payments`)

- **Origem:** Portal da Transparência, download "Despesas – Recebimentos de Recursos por Favorecido". Um arquivo por mês: `AAAAMM_RecebimentosRecursosPorFavorecido.csv`.
- **Formato:** CSV separado por `;`, ISO-8859-1 (Latin-1), quebras de linha CRLF, decimais com vírgula. Valores menores que 1 vêm sem o zero à esquerda (`,8700`).
- **Granularidade:** cada linha é o **total recebido no mês** por um favorecido, de uma unidade gestora, em uma localidade (UF e município). Não são pagamentos individuais. A combinação (favorecido, UG, mês) não é única: o mesmo CPF mascarado aparece para pessoas diferentes.
- **Colunas (12):** código e nome do favorecido, UF, município, órgão superior, órgão, unidade gestora (código e nome), ano/mês e valor recebido.

### Arquivos ingeridos

| Arquivo | Período | Linhas brutas | Excluídas | Gravadas | SHA-256 |
|---|---|---|---|---|---|
| `202501_RecebimentosRecursosPorFavorecido.csv` | 2025-01 | 554.011 | 10.167 | 543.844 | `5c6b95d243b19998f0135f2beac6f07cd2235da97617fd49b341574539dcbb80` |
| `202502_RecebimentosRecursosPorFavorecido.csv` | 2025-02 | 729.402 | 10.406 | 718.996 | `d3f5d803e1f544eae9c44ffd3acd3e1e58733f0b0f360847d37cfc2f09e0f41e` |
| `202503_RecebimentosRecursosPorFavorecido.csv` | 2025-03 | 492.447 | 11.000 | 481.447 | `2e041f33544e554590a2cc7078c3de2da732aef104ef4ab5c87feec440242c4e` |
| `202504_RecebimentosRecursosPorFavorecido.csv` | 2025-04 | 589.077 | 6.841 | 582.236 | `9084ca61e85af3557436ed14d5b3fee8b72fbcdabb6ef121ae57a2d13e4c6f4e` |
| `202505_RecebimentosRecursosPorFavorecido.csv` | 2025-05 | 720.098 | 7.930 | 712.168 | `e87515f4b8551fcf9f8f01f6421350b506997b2def6ea592c3705d1f48ff470c` |
| `202506_RecebimentosRecursosPorFavorecido.csv` | 2025-06 | 628.413 | 8.618 | 619.795 | `3a3e7f5861ed3507ccf060f9554d0407603d1451074dc16258c1c7971038ad8f` |
| `202507_RecebimentosRecursosPorFavorecido.csv` | 2025-07 | 679.943 | 9.086 | 670.857 | `2bef259c28fadcd2f18c7b4cf937b6002b4b1b4d4b1d2e802c5beddc874b972b` |
| `202508_RecebimentosRecursosPorFavorecido.csv` | 2025-08 | 661.949 | 8.896 | 653.053 | `ae2bb2e0d5f59ef5b64faab5c0233ea14aebd4dc2a7a945ea00987e1b2121d04` |
| `202509_RecebimentosRecursosPorFavorecido.csv` | 2025-09 | 805.198 | 8.268 | 796.930 | `46133e1680d833877d3bf984b12d037c01a7754b9323e05ddb1b9e04657e1688` |
| `202510_RecebimentosRecursosPorFavorecido.csv` | 2025-10 | 766.072 | 9.300 | 756.772 | `c1d5c3db4661757fa1dc461c76ae551d052fd404699a571e97da7b2bbc7d2b81` |
| `202511_RecebimentosRecursosPorFavorecido.csv` | 2025-11 | 757.696 | 9.784 | 747.912 | `74c8288513a474d37a78605be05140faf86ee5b4f564cd7218dd38343d58af89` |
| `202512_RecebimentosRecursosPorFavorecido.csv` | 2025-12 | 843.921 | 16.080 | 827.841 | `6e0d10399abfec95c53847caf8279cf86c299aadec6539ef40af62b58cec6fa7` |
| **Total 2025** | | **8.228.227** | **116.376** | **8.111.851** | |

(Hash, linhas e exclusões por critério também ficam na tabela `dataset_files`.)

### Tipos de favorecido

Classificados pelo formato do código (`favored_type`). Contagens de 2025-01:

| Tipo | Formato do código | Linhas |
|---|---|---|
| `individual` | CPF mascarado pelo Portal (`***.123.456-**`) | 395.611 |
| `company` | CNPJ, 14 dígitos | 153.370 |
| `foreign` | Prefixo `EX` (favorecido no exterior) | 2.555 |
| `management_unit` | 6 dígitos (outra unidade gestora federal) | 1.425 |
| `special` | `-1` sem informação, `-11` sigiloso, `-13` folha de pagamento | 755 |
| `other` | Demais códigos alfanuméricos (`RB…`, `TN…`, `PF…`): operações do Tesouro, como dívida pública, resgates e transferências constitucionais | 295 |

### Transformações

- `Valor Recebido`: vírgula vira ponto, zero à esquerda é inserido quando falta; gravado como `numeric(18,2)` (nenhum valor de 2025-01 tem casas não nulas além da segunda). A soma dos valores após o tratamento é idêntica à do arquivo bruto.
- `Ano e mês do lançamento` (`MM/AAAA`) vira data no primeiro dia do mês.
- UF `-1` e município `Sem informação` viram `NULL` (804 linhas em 2025-01). UF `EX` / município `Exterior` são mantidos.
- Pessoas físicas: código e nome não são gravados; ver `docs/decisoes/0002-pseudonimizacao-pessoas-fisicas.md`.
- Arquivo com cabeçalho diferente do esperado ou valor fora do formato numérico é rejeitado por inteiro.

### Exclusões

Aplicadas na ingestão (decisão 0003). Cada linha conta só no primeiro critério que atende.

| Critério | Regra | Linhas excluídas em 2025 |
|---|---|---|
| `treasury_operation` | Favorecido do tipo `other` (operações do Tesouro) | 4.915 |
| `negative_amount` | Valor < 0 (estornos e ajustes) | 54.222 |
| `zero_amount` | Valor = 0 | 57.239 |
| **Total** | | **116.376 (1,4%)** |

### Base gravada (2025, após exclusões)

| Tipo de favorecido | Linhas | Favorecidos distintos | Valor total (R$ bi) |
|---|---|---|---|
| `individual` | 5.578.326 | 1.365.565 | 10,01 |
| `company` | 2.463.532 | 246.855 | 1.016,48 |
| `foreign` | 37.710 | 11.017 | 22,15 |
| `management_unit` | 20.276 | 1.401 | 866,13 |
| `special` | 12.007 | 3 | 11,25 |

- No Postgres, a base completa ocupa 1,33 GB (`payments` 1.034 MB, `favored` 290 MB).
- `management_unit` (transferências entre unidades gestoras federais) é **mantido** (decisão 0003). Tem só 0,25% das linhas, mas 45% do valor total, inclusive unidades do Tesouro (ex.: 170600, de controle da dívida pública).
- A base completa fica apenas no Postgres local; o Supabase recebe só a amostra do experimento (decisão 0004).

## Arquivos descartados

### `202501_Despesas.csv` (Despesas – Execução)

Base agregada por classificação orçamentária (48.873 linhas em 2025-01), sem coluna de favorecido. Não atende ao escopo de pagamentos a favorecidos; substituída pela base acima (ver `docs/decisoes/0001-base-recebimentos-por-favorecido.md`).
