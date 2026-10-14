# 0008 — Desenho do teste das hipóteses H1 e H2

- **Data:** 2026-10-14
- **Status:** aceita (revisão de 2026-10-14)

As hipóteses estão no AGENTS.md (seção 2) e devem ser testadas, não assumidas. O desenho usa só a amostra principal do experimento `principal-2025` (decisões 0005 e 0006), sem rótulos.

## Evidências preliminares (amostra principal)

**Não estacionariedade:** estatística KS entre as distribuições mensais de cada feature (12 meses, 3.531 a 5.663 registros por mês):

| Feature | KS médio entre meses consecutivos | KS médio entre todos os pares | KS máximo |
|---|---|---|---|
| `log_amount` | 0,056 | 0,066 | 0,153 |
| `amount_vs_ug` | 0,060 | 0,074 | 0,219 |
| `amount_vs_favored` | 0,086 | 0,114 | 0,306 |
| `favored_months` | 0,066 | 0,144 | 0,312 |
| `favored_ug_count` | 0,032 | 0,031 | 0,087 |

A distribuição muda de forma moderada entre meses, e mais entre meses distantes do que entre meses consecutivos.

**Atipicidade por célula (mês × tipo):** mínimo, mediana e máximo nas 12 células de cada tipo.

| Indicador | `company` | `individual` |
|---|---|---|
| Registros por célula | 888 / 1.144 / 1.758 | 1.894 / 2.902 / 3.511 |
| Proporção de vetores duplicados | 0,000 / 0,002 / 0,078 | 0,342 / 0,439 / 0,608 |
| Curtose de `log_amount` | −0,07 / 0,09 / 1,24 | 0,66 / 1,64 / 2,62 |
| Assimetria de `log_amount` | −0,35 / −0,20 / −0,08 | −0,41 / 0,07 / 0,29 |

Os dois tipos têm distribuições bem diferentes, e há variação entre meses dentro de cada tipo.

## H2 — Isolation Forest mais estável que o LOF em dados não estacionários

**Operacionalização:** um modelo treinado num mês e aplicado a outro mês deve sinalizar os mesmos registros que um modelo treinado no próprio mês. A perda de concordância mede a sensibilidade à mudança de distribuição.

1. Cada mês da amostra principal é dividido aleatoriamente (semente fixa) em duas metades: **A** (treino) e **B** (avaliação).
2. Para cada algoritmo e cada mês `t`, treina-se um modelo em `A_t` (com o escalador ajustado em `A_t`), com a configuração principal da decisão 0006. O LOF usa `novelty=True` em todos os casos, então todos os algoritmos pontuam registros fora do treino, sem a mistura de modos da decisão 0007.
3. Para cada par de meses `(t, e)` com `t ≠ e` (132 pares): **estabilidade s(t, e)** = Jaccard (p = 1%, e também 5%) entre os sinalizados em `B_e` pelo modelo de `t` e pelo modelo de `e`. O Spearman dos escores também é calculado.
4. **Deriva do par:** média do KS entre `A_t` e `A_e` nas 5 features.
5. **Referência de ruído:** modelo de `e` treinado com outra semente (para o Isolation Forest, que é aleatório), para separar a deriva do acaso.

**Teste:**

- Diferença pareada `d(t, e) = s_IF(t, e) − s_LOF(t, e)`.
- Teste de Wilcoxon pareado unilateral (H2: mediana de `d` > 0).
- Como os pares compartilham meses e não são independentes, o intervalo de confiança da média de `d` é obtido por **bootstrap em blocos**, reamostrando meses de avaliação (10.000 reamostras).
- Complementos:
  - correlação de Spearman entre deriva e `d` (a vantagem cresce com a deriva?);
  - o mesmo resultado para o One-Class SVM, como contexto.

**Custo:** 12 treinos por algoritmo, com 1,8 mil a 2,8 mil registros cada, mais as pontuações. Leva poucos minutos.

## H1 — A distribuição atípica impacta significativamente o desempenho comparativo

**Operacionalização:** sem rótulos, o "desempenho comparativo" é medido por indicadores relativos entre os algoritmos. Se a atipicidade da distribuição importa, esses indicadores devem variar sistematicamente com ela.

1. **Unidades:** 24 células (12 meses × `individual`, `company`). Os demais tipos têm só 200 registros por mês e ficam de fora.
2. Em cada célula, os três algoritmos são treinados e pontuam a própria célula (configuração principal; LOF com a regra de vizinhos aplicada à célula).
3. **Indicadores comparativos por célula:**
   - concordância entre pares (Jaccard p = 1%: IF×LOF, IF×OCSVM, LOF×OCSVM);
   - estabilidade de cada algoritmo frente a subamostras: 5 reajustes em 80% da célula, com Jaccard sobre os registros em comum.
4. **Atipicidade por célula:** proporção de vetores duplicados, curtose e assimetria de `log_amount`.

**Testes:**

- (a) **Efeito do tipo:** Mann–Whitney bilateral de cada indicador entre as 12 células `individual` e as 12 `company`.
- (b) **Associação:** correlação de Spearman entre cada medida de atipicidade e cada indicador nas 24 células, com p-valor por permutação (10.000).
- **Múltiplas comparações:** correção de Holm dentro de cada família de testes. α = 0,05.

**Limitação:** o desenho é observacional, e o tipo de favorecido muda várias características ao mesmo tempo. O teste mostra associação, não causa.

**Complemento opcional (manipulação controlada):** nas células `company`, que quase não têm duplicados, substituir uma fração f ∈ {0%, 10%, 30%, 50%} dos registros por cópias de um mesmo registro típico, imitando as bolsas de valor fixo, e medir como os indicadores mudam. Isso dá evidência causal para um componente específico da atipicidade (massas de duplicados). **Custo:** 12 células × 4 frações × 3 algoritmos, alguns minutos.

## Registro

Implementado em `ml/src/anomalygov_ml/hypotheses.py`, com a configuração em `ml/experiments/configs/principal-2025-hipoteses.toml` (que referencia a configuração principal).

- Cada treino de algoritmo é uma linha em `runs` (seção 7 do AGENTS.md), com as finalidades `h1_cell`, `h1_subsample`, `h1_manipulation`, `h2_month` e `h2_noise`. O subconjunto da amostra principal fica em `runs.subset` (ex.: `{"month": 3, "half": "A"}`). Os escores por registro dessas execuções não são gravados.
- As medidas por unidade (célula ou par de meses) ficam em `hypothesis_units`, e os testes (estatística, efeito, IC, p e p ajustado) em `hypothesis_tests` (migration 005).
- Reexecutar substitui as execuções e os resultados de hipóteses anteriores do mesmo experimento.
- Os resultados entram na seção 7 do relatório em `docs/resultados/`.

## Correção durante a implementação

Na primeira execução, a **retenção** da H1c comparava os sinalizados nos registros não substituídos usando o limiar `p` calculado sobre a célula inteira manipulada. Como as cópias do registro típico nunca são sinalizadas, isso limitava o Jaccard a cerca de `1 − fração`, qualquer que fosse o algoritmo: o Isolation Forest aparecia com exatamente 0,500 em 50%. A retenção (e, por consistência, a estabilidade por subamostra) passou a reaplicar o limiar `p` dentro do mesmo conjunto de registros nos dois lados da comparação. Só a H1 foi reexecutada.

## Situação da revisão (2026-10-14)

| Ponto | Situação |
|---|---|
| 1. Operacionalização da H2 | Aceita |
| 2. Operacionalização da H1 | Aceita |
| 3. Manipulação controlada de duplicados | Incluída |
| 4. α = 0,05 com correção de Holm | Aceito |
