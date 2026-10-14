# 0001 — Base "Recebimentos de Recursos por Favorecido"

- **Data:** 2026-10-14
- **Status:** aceita

## Contexto

O escopo prevê registros de pagamentos a favorecidos do Poder Executivo Federal em 2025. O primeiro arquivo avaliado, `Despesas – Execução`, é agregado por classificação orçamentária e não identifica o favorecido.

## Decisão

Usar a base **Recebimentos de Recursos por Favorecido** (arquivos mensais `AAAAMM_RecebimentosRecursosPorFavorecido.csv`), implementada no adaptador `payments`.

## Consequências

- A unidade de análise é o **total mensal recebido por favorecido, unidade gestora e localidade**, e não o pagamento individual. O artigo deve descrever a anomalia nessa granularidade.
- O volume de 2025 é de 8.228.227 linhas (de 492 mil a 844 mil por mês), o dobro da previsão inicial de 4 milhões.
- A base mistura favorecidos de naturezas muito diferentes (pessoas físicas, empresas, unidades gestoras, exterior, operações do Tesouro). As operações do Tesouro, os valores negativos e os zeros são excluídos na ingestão (decisão 0003).
