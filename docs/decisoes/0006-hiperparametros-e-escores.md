# 0006 — Hiperparâmetros, escores e limiar

- **Data:** 2026-10-14
- **Status:** aceita (revisão de 2026-10-14)

Medições feitas na amostra principal da decisão 0005: semente 42, 56.768 registros, 5 features escaladas com `RobustScaler`, sem deduplicação. O maior grupo de vetores idênticos tem 937 registros, e 36,3% dos registros pertencem a algum grupo duplicado. Ambiente: Python 3.14.4, scikit-learn 1.9.1, numpy 2.5.4, pandas 3.0.6, Intel i5-1135G7 (4 núcleos) com 7,7 GB de RAM.

## 1. Escores e limiar

| Item | Proposta |
|---|---|
| Escore bruto (maior = mais anômalo) | Isolation Forest: `-score_samples(X)`. LOF: `-negative_outlier_factor_`. One-Class SVM: `-score_samples(X)`. |
| Escore normalizado | Posto percentual do escore bruto dentro da execução, em [0, 1] (empates recebem o posto médio). Os escores brutos têm escalas incomparáveis (no LOF, por exemplo, vão de ~1 a 28). |
| Limiar `p` | Principal: **1%**. Todas as métricas também são calculadas para 2% e 5%. |
| Empates no limiar | São sinalizados todos os registros com escore maior ou igual ao quantil `1 − p`. A quantidade real de sinalizados é registrada, porque pode passar de `p·n`. |
| Gravação | Escore bruto, escore normalizado e indicador de sinalizado por registro, na execução principal. |

## 2. Isolation Forest

Estabilidade frente à semente: Jaccard médio dos sinalizados a 1% entre a semente 0 e as sementes 1 a 4.

| `n_estimators` | `max_samples=256` (padrão) | `1024` | `4096` | Tempo (256 / 4096) |
|---|---|---|---|---|
| 100 | 0,65 | 0,69 | 0,69 | 0,6 s / 0,6 s |
| 200 | 0,76 | 0,76 | 0,78 | 0,8 s / 1,1 s |
| 500 | 0,72 | 0,84 | 0,85 | 1,9 s / 2,8 s |
| 1000 | 0,85 | 0,89 | 0,90 | 3,9 s / 5,6 s |

- Com o padrão do scikit-learn (100 árvores), trocar só a semente muda cerca de 1/3 dos sinalizados. Mais árvores reduzem esse ruído a um custo baixo.
- **Configuração principal:** `n_estimators=1000`, `max_samples=4096` (a mais estável medida: Jaccard 0,90 entre sementes, contra 0,85 com o padrão 256), `contamination="auto"` (sem efeito sobre os escores). Uma semente por execução, registrada. O padrão 256 do artigo original do método fica nas variações.
- **Variações** (estabilidade frente aos parâmetros): `n_estimators` ∈ {200, 500, 1000} × `max_samples` ∈ {256, 1024, 4096}.

## 3. One-Class SVM

Kernel RBF. Jaccard dos sinalizados a 1% em relação à configuração de referência (`nu=0,01`, `gamma="scale"`, que nesta amostra vale ≈ 0,022):

| `nu` \ `gamma` | `scale` (≈ 0,022) | 0,1 | 1,0 |
|---|---|---|---|
| 0,005 | 0,67 (2,3 s) | 0,41 (3,4 s) | 0,05 (51 s) |
| 0,01 | referência (3,7 s) | 0,49 (4,3 s) | 0,03 (55 s) |
| 0,05 | 0,46 (41 s) | 0,57 (48 s) | 0,38 (101 s) |

- O One-Class SVM é **muito sensível** aos parâmetros. Com `gamma=1`, o conjunto de sinalizados é praticamente outro (Jaccard ≤ 0,05), e o modelo usa ~5.000 vetores de suporte. Isso é um resultado para o critério de estabilidade frente aos parâmetros.
- **Configuração principal:** `nu=0,01`, `gamma="scale"`. O `nu` é o limite superior da fração de pontos fora da fronteira e combina com `p = 1%`. Sem semente, porque o algoritmo é determinístico.
- **Variações:** `nu` ∈ {0,005; 0,01; 0,05} × `gamma` ∈ {`scale`; 0,1; 1,0}.

## 4. LOF

| `n_neighbors` | Tempo | Escore máximo | Sinalizados a 1% com escore > 1.000 | Jaccard com IF (1000 árvores) / OCSVM |
|---|---|---|---|---|
| 20 | 2,1 s | 6,5 × 10⁹ | 568 de 568 | 0,00 / 0,00 |
| 50 | 2,8 s | 6,2 × 10⁹ | 578 de 578 | 0,00 / 0,00 |
| 937 (= maior grupo) | 31,6 s | 28 | 0 de 568 | 0,02 / 0,10 |
| 987 (maior grupo + 50) | 29,5 s | 23,8 | 0 de 568 | 0,04 / 0,16 |

Maior grupo duplicado em outras amostras do mesmo desenho: 926 (semente 1), 988 (semente 2) e 976 (semente 3).

- **Configuração principal:** `n_neighbors = maior grupo de vetores idênticos da amostra + 50`, calculado e registrado em cada execução. Com `n_neighbors` igual ao maior grupo, o artefato já desaparece, e a margem de 50 evita que a densidade local dependa só do próprio grupo. Usa `novelty=False` (pontua a própria amostra).
- **Variação demonstrativa:** `n_neighbors` ∈ {20, 50}, registrada à parte, para documentar o artefato (decisão 0005). Fica **fora** das métricas comparativas.
- **Variações de parâmetro:** margem ∈ {+50, +200, +500}.

## 5. Escalabilidade

Com a regra do LOF, o número de vizinhos cresce com o tamanho da amostra (o maior grupo duplicado é proporcional a `n`), e a memória das matrizes de vizinhos (distâncias e índices, 16 bytes por par) cresce com `n × n_neighbors`:

| n | Maior grupo (estimado) | `n_neighbors` | Memória estimada |
|---|---|---|---|
| 25.000 | ~410 | ~460 | 0,2 GB |
| 50.000 | ~830 | ~880 | 0,7 GB |
| 100.000 | ~1.650 | ~1.700 | 2,7 GB |
| 200.000 | ~3.300 | ~3.350 | 10,7 GB |

**Decisão:**

- Série de 5 mil, 10 mil, 25 mil e 50 mil registros para os três algoritmos. Os tempos de 100 mil e 200 mil são medidos só para o Isolation Forest e o One-Class SVM.
- O LOF acima de ~75 mil registros não cabe na memória desta máquina com a regra de vizinhos. Isso é registrado como resultado de escalabilidade.
- Mesmo desenho amostral (decisão 0005), sementes registradas, 3 repetições por tamanho.

## 6. Estabilidade frente aos dados

Amostras diferentes têm registros quase totalmente diferentes (57 mil de 8,1 milhões), então os sinalizados não podem ser comparados diretamente. **Decisão:** treinar cada algoritmo nas 10 amostras adicionais (sementes 1 a 10) e **pontuar sempre a amostra principal**. A estabilidade é a concordância (Jaccard dos sinalizados e Spearman dos escores) sobre esses mesmos registros. O LOF precisa de `novelty=True` para pontuar registros fora do treino, o que deve constar no artigo.

## 7. Registro de cada execução (tabela `runs`)

Conforme o AGENTS.md (seção 7):

- algoritmo e hiperparâmetros completos (inclusive o `n_neighbors` derivado e o maior grupo duplicado);
- semente do algoritmo e semente da amostra;
- `p`;
- arquivos e hashes da base;
- critério de amostragem;
- versões de Python, scikit-learn, pandas e numpy;
- tempo de treino e de pontuação;
- número de registros.

## 8. Situação da revisão (2026-10-14)

| Ponto | Situação |
|---|---|
| 1. `max_samples` do Isolation Forest | 4096 na configuração principal |
| 2. Regra do LOF (maior grupo + 50) | Aceita |
| 3. Escalabilidade do LOF limitada a 50 mil | Aceita |
| 4. Estabilidade frente aos dados (treinar em outras amostras, pontuar a principal) | Aceita |
