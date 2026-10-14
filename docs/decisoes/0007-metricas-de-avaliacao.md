# 0007 — Métricas de avaliação

- **Data:** 2026-10-14
- **Status:** proposta (aguardando revisão)

Define como cada critério da seção 2 do AGENTS.md é calculado. Implementado em `ml/src/anomalygov_ml/report.py`. Os valores ficam nas tabelas `run_metrics` e `run_comparisons` (migration 004), e o relatório de cada experimento é gerado em `docs/resultados/<experimento>.md`. Nenhuma métrica depende de rótulos: não há acurácia, precisão, recall nem F1.

Salvo indicação contrária, tudo é calculado sobre a amostra principal, com `p` ∈ {1%, 2%, 5%} e 1% como referência. Os sinalizados seguem a regra de empates da decisão 0006.

| Critério | Cálculo |
|---|---|
| Tempo de execução | `fit_seconds` e `score_seconds` de cada execução (uma thread). A escalabilidade é reportada como média e faixa das 3 repetições por tamanho. No LOF sem `novelty`, a pontuação acontece dentro do treino. |
| Proporção de anômalos | Quantidade e proporção de sinalizados na amostra, e **proporção ponderada** pelos pesos amostrais, que estima a proporção na população (o piso por estrato da decisão 0005 sobrerrepresenta os tipos raros). |
| Concordância e divergência | Jaccard dos sinalizados e Spearman dos escores entre os pares de execuções principais, e número de registros sinalizados por exatamente 1, 2 ou 3 algoritmos. |
| Estabilidade frente aos parâmetros | Jaccard e Spearman de cada variação contra a configuração principal do mesmo algoritmo. |
| Estabilidade frente aos dados | Jaccard e Spearman de cada execução treinada numa amostra adicional (e que pontua a principal) contra a principal: mediana, mínimo e máximo. |
| Características dos sinalizados | Taxa ponderada de sinalização por tipo de favorecido e por mês. Mediana de cada feature e do valor (sem ponderação) na amostra e entre os sinalizados. Órgãos superiores com maior participação ponderada entre os sinalizados. |
| Interpretabilidade | (a) **Substituto global:** árvore de regressão de profundidade 3 treinada para reproduzir o escore normalizado; fidelidade = R² (Molnar, *Interpretable Machine Learning*, cap. "Global Surrogate"). As regras usam limiares nas unidades originais das features. (b) **Feature dominante:** para cada sinalizado, a feature com maior valor absoluto após o `RobustScaler`, que é a mesma escala vista pelos algoritmos. |

## Limitações conhecidas

- **Feature dominante:** favorece features com IQR estreito. `amount_vs_favored` tem a maioria dos valores em 0, então desvios pequenos viram valores escalados grandes. Ela descreve como o algoritmo "vê" o registro, não a importância causal da feature.
- **Substituto global:** imita o escore de todos os registros, não só a cauda sinalizada. Um R² alto significa que a ordenação geral é explicável por poucas regras.
- **Estabilidade frente aos dados do LOF:** compara o modo `novelty=True` (treino em outra amostra) com o modo `novelty=False` (principal).
- **Medianas de features:** não são ponderadas. As taxas por tipo e por mês são.
- **Nomes de órgãos:** vêm truncados em 44 caracteres no arquivo de origem.

## Correção durante a implementação

A primeira versão do substituto usava uma árvore de **classificação** com `class_weight="balanced"` para imitar os sinalizados, com fidelidade medida pelo Jaccard. Com 1% de positivos, o balanceamento fazia a árvore marcar como anômalas regiões inteiras: os dois ramos de um mesmo nó terminavam em `True`, e a fidelidade ficava entre 0,05 e 0,12 por efeito do peso, não dos algoritmos. Ela foi substituída pela árvore de regressão sobre o escore.

## Pontos para decidir

1. Interpretabilidade medida pelo substituto global (R²) mais a feature dominante?
2. Manter as medianas de features sem ponderação?
