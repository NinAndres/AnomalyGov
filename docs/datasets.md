# Bases de dados

Registro de origem, período, transformações, exclusões, valores ausentes e critérios de seleção de cada base utilizada.

## Recebimentos de Recursos por Favorecido (adaptador `payments`)

- **Origem:** Portal da Transparência, download "Despesas – Recebimentos de Recursos por Favorecido". Um arquivo por mês: `AAAAMM_RecebimentosRecursosPorFavorecido.csv`.
- **Formato:** CSV separado por `;`, ISO-8859-1 (Latin-1), quebras de linha CRLF, decimais com vírgula. Valores menores que 1 vêm sem o zero à esquerda (`,8700`).
- **Granularidade:** cada linha é o **total recebido no mês** por um favorecido, de uma unidade gestora, em uma localidade (UF e município). Não são pagamentos individuais. A combinação (favorecido, UG, mês) não é única: o mesmo CPF mascarado aparece para pessoas diferentes.
- **Colunas (12):** código e nome do favorecido, UF, município, órgão superior, órgão, unidade gestora (código e nome), ano/mês e valor recebido.

### Arquivos ingeridos

| Arquivo | Período | Linhas | SHA-256 |
|---|---|---|---|
| `202501_RecebimentosRecursosPorFavorecido.csv` | 2025-01 | 554.011 | `5c6b95d243b19998f0135f2beac6f07cd2235da97617fd49b341574539dcbb80` |

(Hash e linhas também ficam na tabela `dataset_files` a cada ingestão.)

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

### Observações para a seleção do experimento (pendente)

- **Valores negativos:** 3.928 linhas (estornos/ajustes). **Zeros:** 5.953 linhas.
- **Valores extremos:** as maiores magnitudes (até ±4,2 × 10¹¹) são operações financeiras do Tesouro (dívida pública, resgate de aplicações, FPM/FPE), dos tipos `other` e `management_unit`. Elas seriam sinalizadas trivialmente por qualquer algoritmo.
- A ingestão grava todos os registros. O critério de exclusão (tipos de favorecido, negativos, zeros) ainda não foi definido; quando for, registrá-lo aqui e na configuração do experimento.

## Arquivos descartados

### `202501_Despesas.csv` (Despesas – Execução)

Base agregada por classificação orçamentária (48.873 linhas em 2025-01), sem coluna de favorecido. Não atende ao escopo de pagamentos a favorecidos; substituída pela base acima (ver `docs/decisoes/0001-base-recebimentos-por-favorecido.md`).
