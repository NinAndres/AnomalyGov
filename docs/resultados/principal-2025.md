# Resultados: experimento `principal-2025`

Gerado por `python -m anomalygov_ml.report`. Os registros sinalizados são estatisticamente atípicos e **não** indicam fraude ou irregularidade.

## Identificação

| Item | Valor |
|---|---|
| Configuração (SHA-256) | `d8824bf9db76bb4d9790c14a74f70f40b0a09f0d894c622c827198e0ea4bad2c` |
| Amostra principal | id 5, 56.768 registros |
| Base | 12 arquivos, 8.111.851 registros (hashes em `docs/datasets.md`) |
| Features | `log_amount`, `amount_vs_ug`, `amount_vs_favored`, `favored_months`, `favored_ug_count` |
| Ambiente | Python 3.14.4, scikit-learn 1.9.1, numpy 2.5.4, pandas 3.0.6, 8 CPUs lógicas, n_jobs=1 |

## 1. Tempo de execução

Configuração principal, amostra principal:

| Algoritmo | Parâmetros | Treino (s) | Pontuação (s) | Total (s) |
|---|---|---|---|---|
| Isolation Forest | n_estimators=1000, max_samples=4096 | 2,7 | 2,9 | 5,6 |
| LOF | n_neighbors=987, neighbors_margin=50 | 30,0 | 0,0 | 30,0 |
| One-Class SVM | nu=0.01, gamma=scale | 1,6 | 2,3 | 4,0 |

Escalabilidade (tempo total; média e faixa entre repetições; “—” = não executado):

| Registros | Isolation Forest | LOF | One-Class SVM |
|---|---|---|---|
| 5.679 | 2,1 (2,1–2,2) | 0,2 (0,2–0,2) | 0,1 (0,0–0,1) |
| 11.354 | 2,4 (2,4–2,4) | 0,8 (0,7–0,8) | 0,2 (0,2–0,2) |
| 28.383 | 3,6 (3,5–3,7) | 4,3 (4,2–4,5) | 0,9 (0,9–1,0) |
| 56.768 | 6,1 (5,7–6,7) | 26,3 (23,7–30,5) | 5,3 (3,9–7,2) |
| 113.538 | 10,6 (10,0–11,6) | — | 16,9 (15,5–19,8) |
| 226.994 | 21,3 (20,9–21,6) | — | 64,4 (63,4–66,3) |

## 2. Proporção de registros sinalizados

“Ponderada” estima a proporção na população usando os pesos amostrais (decisão 0005).

| Algoritmo | p | Sinalizados | Proporção na amostra | Proporção ponderada |
|---|---|---|---|---|
| Isolation Forest | 1% | 568 | 1,00% | 0,67% |
| Isolation Forest | 2% | 1.136 | 2,00% | 1,43% |
| Isolation Forest | 5% | 2.839 | 5,00% | 3,91% |
| LOF | 1% | 568 | 1,00% | 1,01% |
| LOF | 2% | 1.210 | 2,13% | 2,22% |
| LOF | 5% | 2.839 | 5,00% | 5,18% |
| One-Class SVM | 1% | 569 | 1,00% | 0,76% |
| One-Class SVM | 2% | 1.137 | 2,00% | 1,71% |
| One-Class SVM | 5% | 2.839 | 5,00% | 4,77% |

## 3. Concordância e divergência

| Par | Jaccard p=1% | Jaccard p=2% | Jaccard p=5% | Spearman dos escores |
|---|---|---|---|---|
| Isolation Forest × LOF | 0,103 | 0,091 | 0,100 | 0,225 |
| Isolation Forest × One-Class SVM | 0,347 | 0,306 | 0,269 | -0,023 |
| LOF × One-Class SVM | 0,159 | 0,183 | 0,199 | 0,155 |

| p | Sinalizado por 1 algoritmo | Por 2 | Pelos 3 |
|---|---|---|---|
| 1% | 910 | 240 | 105 |
| 2% | 1.876 | 517 | 191 |
| 5% | 4.598 | 1.256 | 469 |

## 4. Estabilidade

### Frente aos parâmetros

Cada variação comparada com a configuração principal do mesmo algoritmo.

| Algoritmo | Variação | Jaccard p=1% | Jaccard p=5% | Spearman |
|---|---|---|---|---|
| Isolation Forest | n_estimators=200, max_samples=256 | 0,422 | 0,664 | 0,987 |
| Isolation Forest | n_estimators=200, max_samples=1024 | 0,554 | 0,829 | 0,994 |
| Isolation Forest | n_estimators=200, max_samples=4096 | 0,893 | 0,935 | 0,994 |
| Isolation Forest | n_estimators=500, max_samples=256 | 0,409 | 0,663 | 0,987 |
| Isolation Forest | n_estimators=500, max_samples=1024 | 0,651 | 0,864 | 0,995 |
| Isolation Forest | n_estimators=500, max_samples=4096 | 0,912 | 0,953 | 0,999 |
| Isolation Forest | n_estimators=1000, max_samples=256 | 0,422 | 0,672 | 0,989 |
| Isolation Forest | n_estimators=1000, max_samples=1024 | 0,663 | 0,867 | 0,997 |
| LOF | n_neighbors=1137, neighbors_margin=200 | 0,772 | 0,890 | 0,990 |
| LOF | n_neighbors=1437, neighbors_margin=500 | 0,592 | 0,443 | 0,886 |
| One-Class SVM | nu=0.005, gamma=scale | 0,665 | 0,801 | 0,940 |
| One-Class SVM | nu=0.005, gamma=0.1 | 0,412 | 0,178 | 0,446 |
| One-Class SVM | nu=0.005, gamma=1.0 | 0,054 | 0,110 | 0,019 |
| One-Class SVM | nu=0.01, gamma=0.1 | 0,494 | 0,280 | 0,443 |
| One-Class SVM | nu=0.01, gamma=1.0 | 0,026 | 0,085 | 0,024 |
| One-Class SVM | nu=0.05, gamma=scale | 0,456 | 0,513 | 0,810 |
| One-Class SVM | nu=0.05, gamma=0.1 | 0,568 | 0,412 | 0,424 |
| One-Class SVM | nu=0.05, gamma=1.0 | 0,382 | 0,209 | 0,031 |

### Frente aos dados

Treino em cada amostra adicional, pontuação da amostra principal. Mediana (mínimo–máximo) entre as amostras. O LOF usa `novelty=True` nessas execuções e `novelty=False` na principal.

| Algoritmo | Amostras | Jaccard p=1% | Jaccard p=5% | Spearman (mediana) |
|---|---|---|---|---|
| Isolation Forest | 10 | 0,890 (0,859–0,909) | 0,941 (0,931–0,949) | 0,998 |
| LOF | 10 | 0,921 (0,856–0,945) | 0,954 (0,939–0,967) | 0,994 |
| One-Class SVM | 10 | 0,800 (0,788–0,825) | 0,830 (0,761–0,871) | 0,985 |

## 5. Características dos registros sinalizados (p = 1%)

### Por tipo de favorecido

Taxa = proporção ponderada de registros do tipo que foram sinalizados.

| Tipo | Na população | Taxa Isolation Forest | Taxa LOF | Taxa One-Class SVM |
|---|---|---|---|---|
| `company` | 30,4% | 1,48% | 0,32% | 1,34% |
| `foreign` | 0,5% | 1,51% | 1,66% | 1,29% |
| `individual` | 68,8% | 0,28% | 1,31% | 0,49% |
| `management_unit` | 0,2% | 7,65% | 1,26% | 5,48% |
| `special` | 0,1% | 1,11% | 0,00% | 1,40% |

### Por mês (não estacionariedade)

| Mês | Taxa Isolation Forest | Taxa LOF | Taxa One-Class SVM |
|---|---|---|---|
| 2025-01 | 0,75% | 0,64% | 1,08% |
| 2025-02 | 0,45% | 0,97% | 0,69% |
| 2025-03 | 0,67% | 0,85% | 0,64% |
| 2025-04 | 0,79% | 1,12% | 0,89% |
| 2025-05 | 0,43% | 1,01% | 0,56% |
| 2025-06 | 0,58% | 0,97% | 0,53% |
| 2025-07 | 0,80% | 1,35% | 0,92% |
| 2025-08 | 0,53% | 0,96% | 0,54% |
| 2025-09 | 0,52% | 0,66% | 0,60% |
| 2025-10 | 0,65% | 0,81% | 0,85% |
| 2025-11 | 1,01% | 1,01% | 1,01% |
| 2025-12 | 0,88% | 1,58% | 0,86% |

### Features: mediana na amostra × mediana dos sinalizados

| Feature | Amostra | Sinalizados Isolation Forest | Sinalizados LOF | Sinalizados One-Class SVM |
|---|---|---|---|---|
| `log_amount` | 6,94 | 10,58 | 7,19 | 7,47 |
| `amount_vs_ug` | 0,00 | 2,57 | 0,37 | 0,06 |
| `amount_vs_favored` | 0,00 | 0,21 | 10,96 | 0,00 |
| `favored_months` | 9,00 | 12,00 | 10,00 | 12,00 |
| `favored_ug_count` | 0,69 | 1,39 | 0,69 | 1,10 |
| valor (R$) | 1.032,00 | 39.429,62 | 1.330,75 | 1.756,63 |

### Órgãos superiores com mais sinalizados (contagem ponderada)

- **Isolation Forest:** Ministério da Educação (39,7%); Ministério da Defesa (16,3%); Ministério da Justiça e Segurança Pública (5,5%); Ministério da Saúde (5,0%); Ministério da Previdência Social (4,6%)
- **LOF:** Ministério da Educação (66,1%); Ministério da Integração e do Desenvolvime (9,9%); Ministério da Ciência, Tecnologia e Inovaç (5,4%); Ministério da Defesa (3,3%); Ministério da Saúde (3,0%)
- **One-Class SVM:** Ministério da Educação (46,8%); Ministério da Defesa (12,2%); Ministério da Saúde (6,1%); Ministério da Justiça e Segurança Pública (4,7%); Ministério da Previdência Social (4,2%)

## 6. Interpretabilidade

**Substituto global:** árvore de regressão de profundidade 3 treinada para reproduzir o escore normalizado de cada algoritmo a partir das features. Fidelidade = R² entre a previsão da árvore e o escore; quanto maior, mais a lógica do algoritmo é explicável por poucas regras simples. Nas regras, `value` é o escore normalizado médio da folha (perto de 1 = anômalo).

| Algoritmo | Fidelidade (R²) |
|---|---|
| Isolation Forest | 0,590 |
| LOF | 0,220 |
| One-Class SVM | 0,520 |

**Feature dominante:** feature com maior desvio robusto (|valor escalado|) em cada registro sinalizado; proporção dos sinalizados por feature.

| Feature | Isolation Forest | LOF | One-Class SVM |
|---|---|---|---|
| `log_amount` | 4,2% | 3,3% | 3,2% |
| `amount_vs_ug` | 32,6% | 3,7% | 9,8% |
| `amount_vs_favored` | 33,1% | 77,8% | 63,6% |
| `favored_months` | 0,0% | 15,1% | 0,0% |
| `favored_ug_count` | 30,1% | 0,0% | 23,4% |

<details><summary>Regras da árvore substituta: Isolation Forest</summary>

```
|--- favored_ug_count <= 1.24
|   |--- amount_vs_ug <= 1.74
|   |   |--- amount_vs_ug <= -1.04
|   |   |   |--- value: [0.68]
|   |   |--- amount_vs_ug >  -1.04
|   |   |   |--- value: [0.33]
|   |--- amount_vs_ug >  1.74
|   |   |--- amount_vs_ug <= 2.70
|   |   |   |--- value: [0.66]
|   |   |--- amount_vs_ug >  2.70
|   |   |   |--- value: [0.86]
|--- favored_ug_count >  1.24
|   |--- log_amount <= 4.97
|   |   |--- log_amount <= 3.71
|   |   |   |--- value: [0.95]
|   |   |--- log_amount >  3.71
|   |   |   |--- value: [0.88]
|   |--- log_amount >  4.97
|   |   |--- amount_vs_ug <= 3.67
|   |   |   |--- value: [0.76]
|   |   |--- amount_vs_ug >  3.67
|   |   |   |--- value: [0.90]
```

</details>

<details><summary>Regras da árvore substituta: LOF</summary>

```
|--- favored_ug_count <= 2.60
|   |--- amount_vs_ug <= -1.25
|   |   |--- amount_vs_favored <= -0.55
|   |   |   |--- value: [0.69]
|   |   |--- amount_vs_favored >  -0.55
|   |   |   |--- value: [0.81]
|   |--- amount_vs_ug >  -1.25
|   |   |--- log_amount <= 8.77
|   |   |   |--- value: [0.47]
|   |   |--- log_amount >  8.77
|   |   |   |--- value: [0.68]
|--- favored_ug_count >  2.60
|   |--- amount_vs_favored <= 1.90
|   |   |--- log_amount <= 4.81
|   |   |   |--- value: [0.62]
|   |   |--- log_amount >  4.81
|   |   |   |--- value: [0.26]
|   |--- amount_vs_favored >  1.90
|   |   |--- amount_vs_favored <= 2.64
|   |   |   |--- value: [0.59]
|   |   |--- amount_vs_favored >  2.64
|   |   |   |--- value: [0.84]
```

</details>

<details><summary>Regras da árvore substituta: One-Class SVM</summary>

```
|--- favored_ug_count <= 0.90
|   |--- amount_vs_favored <= 1.67
|   |   |--- log_amount <= 6.48
|   |   |   |--- value: [0.69]
|   |   |--- log_amount >  6.48
|   |   |   |--- value: [0.52]
|   |--- amount_vs_favored >  1.67
|   |   |--- amount_vs_favored <= 2.56
|   |   |   |--- value: [0.79]
|   |   |--- amount_vs_favored >  2.56
|   |   |   |--- value: [0.93]
|--- favored_ug_count >  0.90
|   |--- log_amount <= 3.44
|   |   |--- amount_vs_ug <= -5.09
|   |   |   |--- value: [0.93]
|   |   |--- amount_vs_ug >  -5.09
|   |   |   |--- value: [0.75]
|   |--- log_amount >  3.44
|   |   |--- amount_vs_favored <= 3.24
|   |   |   |--- value: [0.24]
|   |   |--- amount_vs_favored >  3.24
|   |   |   |--- value: [0.69]
```

</details>

## 7. Hipóteses (decisão 0008)

p ajustado pela correção de Holm dentro de cada família; significativo quando p ajustado < 0,05. Efeito: diferença média dos Jaccard (H2, com IC 95% por bootstrap em blocos de meses), correlação bisserial de postos (H1a), Spearman (H1b) ou W de Kendall (H1c). As medianas descrevem os indicadores.


### H2: Isolation Forest × LOF entre meses (teste unilateral: IF mais estável)

2 de 3 testes significativos.

| Variável | n | Teste | Estatística | Efeito | IC 95% | p | p ajustado | Medianas |
|---|---|---|---|---|---|---|---|---|
| `jaccard_if_minus_lof_p01` | 132 | wilcoxon_greater | 8.085,000 | 0,203 | 0,163 a 0,242 | 2.8e-20 | **5.7e-20** | IF 0,677; outro 0,481; ruído de semente do IF 0,886 |
| `jaccard_if_minus_lof_p05` | 132 | wilcoxon_greater | 8.778,000 | 0,399 | 0,373 a 0,424 | 1e-23 | **3.1e-23** | IF 0,788; outro 0,375; ruído de semente do IF 0,962 |
| `drift_vs_jaccard_if_minus_lof_p01` | 132 | spearman_permutation | 0,145 | 0,145 |  | 0.097 | 0.097 |  |

### Contexto da H2: Isolation Forest × One-Class SVM (bilateral)

3 de 3 testes significativos.

| Variável | n | Teste | Estatística | Efeito | IC 95% | p | p ajustado | Medianas |
|---|---|---|---|---|---|---|---|---|
| `jaccard_if_minus_ocsvm_p01` | 132 | wilcoxon_two-sided | 3,000 | 0,302 | 0,264 a 0,337 | 4.8e-23 | **9.6e-23** | IF 0,677; outro 0,373; ruído de semente do IF 0,886 |
| `jaccard_if_minus_ocsvm_p05` | 132 | wilcoxon_two-sided | 0,000 | 0,364 | 0,339 a 0,399 | 2.1e-23 | **6.3e-23** | IF 0,788; outro 0,430; ruído de semente do IF 0,962 |
| `drift_vs_jaccard_if_minus_ocsvm_p01` | 132 | spearman_permutation | 0,218 | 0,218 |  | 0.013 | **0.013** |  |

### H1a: indicadores por tipo de favorecido (`individual` × `company`)

3 de 6 testes significativos.

| Variável | n | Teste | Estatística | Efeito | IC 95% | p | p ajustado | Medianas |
|---|---|---|---|---|---|---|---|---|
| `jaccard_if_lof` | 24 | mann_whitney | 92,500 | 0,285 |  | 0.25 | 0.5 | individual 0,255; company 0,215 |
| `jaccard_if_ocsvm` | 24 | mann_whitney | 122,500 | 0,701 |  | 0.0038 | **0.015** | individual 0,213; company 0,101 |
| `jaccard_lof_ocsvm` | 24 | mann_whitney | 134,500 | 0,868 |  | 0.00034 | **0.0017** | individual 0,172; company 0,062 |
| `stability_if` | 24 | mann_whitney | 53,000 | -0,264 |  | 0.29 | 0.5 | individual 0,881; company 0,896 |
| `stability_lof` | 24 | mann_whitney | 106,000 | 0,472 |  | 0.053 | 0.16 | individual 0,926; company 0,805 |
| `stability_ocsvm` | 24 | mann_whitney | 140,000 | 0,944 |  | 9.7e-05 | **0.00058** | individual 0,257; company 0,144 |

### H1b: associação entre atipicidade da célula e indicadores

4 de 18 testes significativos.

| Variável | n | Teste | Estatística | Efeito | IC 95% | p | p ajustado | Medianas |
|---|---|---|---|---|---|---|---|---|
| `duplicate_share_vs_jaccard_if_lof` | 24 | spearman_permutation | -0,092 | -0,092 |  | 0.67 | 1 |  |
| `duplicate_share_vs_jaccard_if_ocsvm` | 24 | spearman_permutation | 0,514 | 0,514 |  | 0.011 | 0.14 |  |
| `duplicate_share_vs_jaccard_lof_ocsvm` | 24 | spearman_permutation | 0,699 | 0,699 |  | 0.0008 | **0.014** |  |
| `duplicate_share_vs_stability_if` | 24 | spearman_permutation | -0,226 | -0,226 |  | 0.29 | 1 |  |
| `duplicate_share_vs_stability_lof` | 24 | spearman_permutation | 0,334 | 0,334 |  | 0.11 | 0.84 |  |
| `duplicate_share_vs_stability_ocsvm` | 24 | spearman_permutation | 0,786 | 0,786 |  | 0.0001 | **0.0018** |  |
| `kurtosis_vs_jaccard_if_lof` | 24 | spearman_permutation | 0,047 | 0,047 |  | 0.82 | 1 |  |
| `kurtosis_vs_jaccard_if_ocsvm` | 24 | spearman_permutation | 0,423 | 0,423 |  | 0.042 | 0.42 |  |
| `kurtosis_vs_jaccard_lof_ocsvm` | 24 | spearman_permutation | 0,568 | 0,568 |  | 0.0046 | 0.064 |  |
| `kurtosis_vs_stability_if` | 24 | spearman_permutation | -0,340 | -0,340 |  | 0.11 | 0.84 |  |
| `kurtosis_vs_stability_lof` | 24 | spearman_permutation | 0,211 | 0,211 |  | 0.32 | 1 |  |
| `kurtosis_vs_stability_ocsvm` | 24 | spearman_permutation | 0,604 | 0,604 |  | 0.0017 | **0.027** |  |
| `skewness_vs_jaccard_if_lof` | 24 | spearman_permutation | 0,365 | 0,365 |  | 0.08 | 0.72 |  |
| `skewness_vs_jaccard_if_ocsvm` | 24 | spearman_permutation | 0,446 | 0,446 |  | 0.029 | 0.32 |  |
| `skewness_vs_jaccard_lof_ocsvm` | 24 | spearman_permutation | 0,611 | 0,611 |  | 0.0018 | **0.027** |  |
| `skewness_vs_stability_if` | 24 | spearman_permutation | -0,026 | -0,026 |  | 0.9 | 1 |  |
| `skewness_vs_stability_lof` | 24 | spearman_permutation | 0,192 | 0,192 |  | 0.36 | 1 |  |
| `skewness_vs_stability_ocsvm` | 24 | spearman_permutation | 0,469 | 0,469 |  | 0.021 | 0.25 |  |

### H1c: manipulação controlada de duplicados (células `company`)

4 de 6 testes significativos.

| Variável | n | Teste | Estatística | Efeito | IC 95% | p | p ajustado | Medianas |
|---|---|---|---|---|---|---|---|---|
| `jaccard_if_lof` | 12 | friedman | 10,500 | 0,292 |  | 0.015 | **0.044** | 0%: 0,215; 10%: 0,200; 30%: 0,200; 50%: 0,287 |
| `jaccard_if_ocsvm` | 12 | friedman | 2,048 | 0,057 |  | 0.56 | 0.74 | 0%: 0,101; 10%: 0,116; 30%: 0,106; 50%: 0,160 |
| `jaccard_lof_ocsvm` | 12 | friedman | 3,134 | 0,087 |  | 0.37 | 0.74 | 0%: 0,062; 10%: 0,108; 30%: 0,091; 50%: 0,131 |
| `retention_if` | 12 | friedman | 12,351 | 0,343 |  | 0.0063 | **0.025** | 0%: 1,000; 10%: 1,000; 30%: 0,923; 50%: 0,789 |
| `retention_lof` | 12 | friedman | 31,619 | 0,878 |  | 6.3e-07 | **3.8e-06** | 0%: 1,000; 10%: 0,609; 30%: 0,359; 50%: 0,267 |
| `retention_ocsvm` | 12 | friedman | 29,897 | 0,830 |  | 1.5e-06 | **7.3e-06** | 0%: 1,000; 10%: 0,222; 30%: 0,095; 50%: 0,029 |

## Apêndice: artefato do LOF com vetores duplicados

Execuções demonstrativas, fora das métricas comparativas (decisão 0005).

| Parâmetros | Escore máximo | Sinalizados com escore > 1.000 | Jaccard com o LOF principal |
|---|---|---|---|
| n_neighbors=20 | 6.46e+09 | 568 de 568 | 0,012 |
| n_neighbors=50 | 6.20e+09 | 578 de 578 | 0,003 |
