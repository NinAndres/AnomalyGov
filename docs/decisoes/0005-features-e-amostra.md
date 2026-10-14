# 0005 — Features e amostra do experimento

- **Data:** 2026-10-14
- **Status:** aceita (revisão de 2026-10-14)

Os números abaixo vêm da base de 2025 já tratada (8.111.851 registros, decisões 0003 e 0004) e de testes feitos nesta máquina.

## 1. Unidade de análise

Cada registro de `payments`: total recebido no mês por um favorecido, de uma unidade gestora (UG), em uma localidade.

## 2. Features propostas

Cinco features numéricas, todas com interpretação direta:

| # | Feature | Definição | O que captura |
|---|---|---|---|
| 1 | `log_amount` | `ln(1 + valor)` | Magnitude do valor. O log é necessário porque os valores vão de R$ 0,01 a R$ 1,5 × 10¹¹ (mediana de R$ 700 para pessoa física e de R$ 3.895 para empresa). |
| 2 | `amount_vs_ug` | `log_amount` − mediana de `log_amount` da UG pagadora no ano | Valor atípico **para a unidade que paga**. |
| 3 | `amount_vs_favored` | (`log_amount` − mediana do favorecido) / (MAD do favorecido + 0,1) | Valor atípico **para o próprio favorecido** (z robusto). Vale 0 para quem tem um único registro. |
| 4 | `favored_months` | Número de meses de 2025 em que o favorecido recebeu (1 a 12) | Recorrência: 30,7% dos favorecidos recebem em só 1 mês e 3,8% nos 12. |
| 5 | `favored_ug_count` | `ln(1 + nº de UGs distintas que pagaram o favorecido no ano)` | Abrangência: 88,5% recebem de uma única UG, e alguns de mais de 2.000. |

**Pré-processamento:** `RobustScaler` (mediana e IQR), ajustado na amostra da execução. Os três algoritmos recebem a mesma matriz escalada, sem deduplicação (seção 3).

### Candidatas descartadas

| Feature | Motivo |
|---|---|
| Valor vs. mediana do tipo de favorecido e do mês | Correlação de Spearman de 0,88 com `log_amount`, quase redundante. |
| Participação no total da UG no mês (`share_ug_month`) | Correlação de 0,41 com `amount_vs_ug`, e a soma mensal da UG mistura escalas muito diferentes. **Descartada** (revisão de 2026-10-14). |
| Tipo de favorecido (one-hot) | Variável categórica distorce as distâncias do LOF e do One-Class SVM. O tipo é usado na estratificação e na análise dos sinalizados. |
| UF, órgão superior | Categóricas de alta cardinalidade, mesmo problema. Ficam como colunas de exibição e de análise. |

Correlações de Spearman entre as features propostas (amostra de 200 mil registros): a maior é 0,72 (`log_amount` × `amount_vs_ug`). Todas as demais ficam abaixo de 0,55.

### Ressalva temporal

As features 2 a 5 usam o ano inteiro, então um registro de janeiro "conhece" o comportamento do favorecido até dezembro. **Aceito**: a análise é retrospectiva do ano de 2025, e isso deve constar no artigo.

## 3. Vetores duplicados

Na amostra de teste, **36% dos registros têm um vetor de features idêntico ao de outro registro**. O maior grupo tem 975 registros iguais: bolsas de valor fixo pagas todo mês pela mesma UG. Com `n_neighbors=20`, o LOF fica indefinido nesses grupos. O scikit-learn avisa "Duplicate values are leading to incorrect results", e os escores chegam a −4 × 10⁹.

**Decisão: não deduplicar.** Os três algoritmos recebem a mesma amostra, com a distribuição real dos dados, inclusive os duplicados. A deduplicação foi avaliada (abaixo) e descartada porque altera o comportamento do Isolation Forest e do One-Class SVM.

### Impacto da deduplicação no Isolation Forest e no One-Class SVM

Teste na amostra principal (56.768 registros, 39.076 vetores distintos), com três formas de treino:

- **A:** todos os registros (com duplicados);
- **B:** vetores distintos;
- **C:** vetores distintos com `sample_weight` = número de registros do vetor.

Nas três formas, todos os registros são pontuados e o limiar `p` é aplicado sobre eles.

**Isolation Forest** (100 árvores; Jaccard dos sinalizados em p = 1% / 2% / 5%):

| Comparação | Spearman dos escores | Jaccard |
|---|---|---|
| A × A com outra semente (4 sementes, referência de ruído) | 0,976 a 0,981 | 0,60–0,67 / 0,63–0,72 / 0,77–0,79 |
| A × B (2 sementes) | 0,964 a 0,977 | 0,59–0,70 / 0,65–0,72 / 0,77–0,78 |
| A × C (2 sementes) | 0,983 a 0,988 | 0,61–0,70 / 0,66–0,78 / 0,77–0,84 |

**One-Class SVM** (determinístico, `nu=0,01`, `gamma=scale`):

| Comparação | Spearman dos escores | Jaccard p = 1% / 2% / 5% |
|---|---|---|
| A × B | 0,983 | 0,78 / 0,78 / 0,82 |
| A × C | 0,980 | 0,87 / 0,80 / 0,90 |

Observações:

- **Isolation Forest:** o efeito da deduplicação (B ou C) fica dentro da variação causada só pela troca de semente. Na prática, não dá para distinguir as duas.
- **One-Class SVM:** a deduplicação simples (B) muda 22% dos sinalizados a 1%. Com pesos (C), a mudança cai para 13%.
- **Duplicados entre os sinalizados:** os registros com vetor duplicado são 36% da amostra, mas apenas 0,9% a 5,1% dos sinalizados em qualquer forma. Os duplicados quase nunca são anomalias. O problema deles é invalidar o LOF, não mudar quem é sinalizado.
- **Composição por tipo** (Isolation Forest, semente 0, p = 1%): `management_unit` passa de 42,6% (A) para 49,8% (B) e 51,6% (C), e `company` cai de 41,4% para 32,6% e 26,9%. Não foi medido quanto essa composição varia entre sementes.
- **Tempo:** sem diferença relevante no Isolation Forest (~0,35 a 0,39 s). No One-Class SVM, A leva 3,7 s, B 2,4 s e C 3,0 s.
- **Achado paralelo:** com 100 árvores, o Isolation Forest muda de 33% a 40% dos sinalizados a 1% só ao trocar a semente. Isso pesa na avaliação de estabilidade (H2), e a grade de hiperparâmetros deve incluir mais árvores.
- A concordância entre Isolation Forest e One-Class SVM (Jaccard a 1%) fica entre 0,18 e 0,19 nas três formas.

### Consequência para o LOF (medida na amostra principal, com duplicados)

| `n_neighbors` | Tempo | Escore máximo | Sinalizados a 1% com escore > 1.000 | Jaccard com IF / OCSVM |
|---|---|---|---|---|
| 20 | 1,4 s | 5,7 × 10⁹ | 568 de 568 | 0,00 / 0,00 |
| 50 | 1,9 s | 4,4 × 10⁹ | 571 de 571 | 0,00 / 0,00 |
| 1.000 | 36,3 s | 24,1 | 0 de 568 | 0,04 / 0,16 |

- Com `n_neighbors` menor que o maior grupo de vetores idênticos (975 na amostra principal), **todos** os sinalizados do LOF são artefato numérico. São registros vizinhos de grupos duplicados, cuja densidade local é tratada como quase infinita. Com `n_neighbors=20` ou `50`, 90% dos sinalizados são pessoas físicas, e a concordância com os outros dois algoritmos é nula.
- Com `n_neighbors` acima do maior grupo, os escores voltam a uma faixa interpretável.
- Isso é um resultado observado: a concentração de registros idênticos (bolsas de valor fixo) afeta diretamente o LOF, o que se relaciona com a H1.
- A escolha de `n_neighbors` fica para a decisão sobre hiperparâmetros. Ela deve considerar o tamanho do maior grupo duplicado em cada amostra (registrado em cada execução) e o custo de tempo, que cresce com `n_neighbors`.

## 4. Amostra

| Item | Proposta |
|---|---|
| População | `payments` de 2025 após as exclusões (8.111.851 registros) |
| Estratos | Mês (12) × tipo de favorecido (5) = 60 estratos |
| Alocação | Proporcional para um total de 50.000, com **piso de 200 por estrato** (ou o estrato inteiro, se menor). **Aceita** (revisão de 2026-10-14). |
| Tamanho resultante | 56.768 registros |
| Pesos | Cada registro guarda o peso amostral (tamanho do estrato / sorteados), para estimar proporções na população |
| Semente principal | `random_state = 42` |
| Estabilidade nos dados | 10 amostras adicionais com sementes 1 a 10, mesmo desenho |
| Escalabilidade | Tempos com 5 mil, 10 mil, 25 mil, 50 mil, 100 mil e 200 mil registros, executados no banco local. Só os tempos vão para o Supabase. |

**Por que o piso:** com alocação puramente proporcional, `foreign`, `management_unit` e `special` teriam juntos cerca de 430 registros no ano inteiro (menos de 1%), poucos para caracterizar os sinalizados desses tipos. O piso eleva esses tipos para 12,7% da amostra. Por isso a proporção de anômalos por tipo deve ser reportada com os pesos.

Alocação resultante por mês: `individual` de 1.894 a 3.511, `company` de 888 a 1.758, e os demais tipos com 200 cada.

### Tempos medidos (amostra escalada, 5 features, parâmetros padrão)

| n | Isolation Forest | LOF | One-Class SVM (`nu=0,01`) |
|---|---|---|---|
| 5.000 | 0,1 s | 0,1 s | < 0,1 s |
| 10.000 | 0,1 s | 0,1 s | 0,1 s |
| 25.000 | 0,2 s | 0,5 s | 0,8 s |
| 50.000 | 0,4 s | 1,2 s | não medido |

Esses tempos são preliminares: foram medidos sem a deduplicação e são de uma única execução. Mesmo assim, mostram que uma amostra principal de ~57 mil registros é viável para os três algoritmos, e que a série de escalabilidade pode ir além de 50 mil.

## 5. Ligação com as hipóteses

- **H1 (distribuição atípica afeta a comparação):** comparar a execução na amostra estratificada com execuções por tipo de favorecido (`individual` e `company` separados), cujas distribuições de valor são muito diferentes.
- **H2 (Isolation Forest mais estável que o LOF em dados não estacionários):** a estratificação por mês permite rodar os algoritmos mês a mês e medir a concordância dos sinalizados entre meses. As 10 amostras com sementes diferentes medem a estabilidade frente aos dados.

## 6. Situação da revisão (2026-10-14)

| Ponto | Situação |
|---|---|
| 1. Deduplicação dos vetores | Não deduplicar; os três algoritmos recebem a mesma amostra |
| 2. Piso de 200 por estrato | Aceito |
| 3. Features calculadas sobre o ano inteiro | Mantidas; ressalva registrada no artigo |
| 4. `share_ug_month` como sexta feature | Descartada |
