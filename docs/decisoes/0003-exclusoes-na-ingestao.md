# 0003 — Exclusões na ingestão

- **Data:** 2026-10-14
- **Status:** aceita

## Contexto

A base de recebimentos por favorecido inclui registros que não representam recebimentos de favorecidos e que distorcem a detecção de anomalias:

- **Operações do Tesouro** (`favored_type = 'other'`, códigos `RB…`, `TN…`, `PF…`): dívida pública, resgate de aplicações, transferências constitucionais (FPM/FPE). Em 2025-01 somam R$ 621 bilhões em 295 linhas, com valores de até ±4,2 × 10¹¹, e seriam sinalizadas trivialmente por qualquer algoritmo.
- **Valores negativos** (estornos e ajustes) e **valores zero**, que não representam recebimento efetivo.

## Decisão

O adaptador `payments` remove na ingestão, nesta ordem:

1. `treasury_operation`: favorecido do tipo `other`;
2. `negative_amount`: valor menor que zero;
3. `zero_amount`: valor igual a zero.

Cada linha é contada só no primeiro critério que atende. As contagens por critério ficam em `dataset_files.excluded_rows`, o total do arquivo bruto em `row_count` e o total gravado em `loaded_row_count`.

## Consequências

- As exclusões valem para os modos `experiment` e `exploration`.
- O arquivo bruto e o SHA-256 dele continuam registrados, então o processamento é reproduzível. Mudar o critério exige reingerir os arquivos.
- Favorecidos do tipo `management_unit` (transferências entre unidades gestoras federais, inclusive unidades do Tesouro como a 170600, de controle da dívida pública) são **mantidos**. Em 2025 são 0,25% das linhas, mas 45% do valor total. A análise deve levar em conta que esses valores extremos tendem a ser sinalizados.
