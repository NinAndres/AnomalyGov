# 0001 — Base "Recebimentos de Recursos por Favorecido"

- **Data:** 2026-10-14
- **Status:** aceita

## Contexto

O escopo prevê registros de pagamentos a favorecidos do Poder Executivo Federal em 2025. O primeiro arquivo avaliado, `Despesas – Execução`, é agregado por classificação orçamentária e não identifica o favorecido.

## Decisão

Usar a base **Recebimentos de Recursos por Favorecido** (arquivos mensais `AAAAMM_RecebimentosRecursosPorFavorecido.csv`), implementada no adaptador `payments`.

## Consequências

- A unidade de análise é o **total mensal recebido por favorecido, unidade gestora e localidade**, e não o pagamento individual. O artigo deve descrever a anomalia nessa granularidade.
- O volume é de cerca de 554 mil linhas por mês (estimativa de 6,6 milhões em 2025), acima da previsão inicial de 4 milhões.
- A base mistura favorecidos de naturezas muito diferentes (pessoas físicas, empresas, unidades gestoras, exterior, operações do Tesouro). O critério de seleção para o experimento ainda está pendente (ver `docs/datasets.md`).
