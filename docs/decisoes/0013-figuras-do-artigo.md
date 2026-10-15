# 0013 — Figuras do artigo

- **Data:** 2026-10-15
- **Status:** aceita

## Contexto

O artigo precisa de figuras estáticas, em resolução de impressão, com os mesmos números do relatório (`docs/resultados/`) e da aplicação (decisão 0012). Capturas de tela dos gráficos da aplicação não servem: a resolução é baixa e elas não são reproduzíveis.

## Decisões

- **Módulo `anomalygov_ml.figures`** (`python -m anomalygov_ml.figures <experimento>`), com **matplotlib** como dependência opcional (`pip install -e ".[figures]"`, incluída em `dev`). O worker não precisa dela.
- **Nada é recalculado.** O módulo lê só as tabelas gravadas por `anomalygov_ml.report` no banco local: `run_metrics`, `run_comparisons`, `run_profiles`, `run_surrogates`, `experiment_overlaps` e `hypothesis_tests`. Se o relatório não tiver sido gerado, o módulo para com uma mensagem.
- **Saída local, fora do Git** em `docs/resultados/figuras/<experimento>/`: 13 figuras, cada uma em PNG (300 dpi) e SVG, numeradas na ordem sugerida para o texto, mais `legendas.md` com uma legenda sugerida por figura (cerca de 1,3 MB). As figuras não são versionadas: são derivadas das tabelas do relatório e podem ser geradas de novo a qualquer momento com o comando acima. A regeneração produz arquivos idênticos quando os dados não mudam (metadados fixos).
- **Formato para o artigo:** largura de 16 cm (texto de uma página A4 com margens ABNT), fonte sem serifa de 9 pt, números com vírgula decimal e textos em português. As figuras não têm título: o título e a fonte entram na legenda, no texto do artigo.
- **Cores:** as mesmas da aplicação (decisão 0012). Nas linhas e pontos, cada algoritmo também tem um marcador próprio (círculo, quadrado, triângulo), para que as séries continuem distinguíveis em impressão em tons de cinza.

## Figuras

| Nº | Arquivo | Critério |
|---|---|---|
| 1 | `tempo-execucao` | Tempo de execução |
| 2 | `escalabilidade` | Tempo de execução (escala) |
| 3 | `proporcao-ponderada` | Proporção de sinalizados |
| 4 | `concordancia-jaccard` | Concordância e divergência |
| 5 | `sobreposicao` | Concordância e divergência |
| 6 | `estabilidade-parametros` | Estabilidade frente aos parâmetros |
| 7 | `estabilidade-dados` | Estabilidade frente aos dados |
| 8 | `taxa-por-tipo` | Características dos sinalizados |
| 9 | `taxa-por-mes` | Características dos sinalizados (não estacionariedade) |
| 10 | `feature-dominante` | Interpretabilidade |
| 11 | `fidelidade-substituto` | Interpretabilidade |
| 12 | `h2-estabilidade-meses` | Hipótese H2 |
| 13 | `h1c-retencao` | Hipótese H1 (manipulação controlada) |

## Consequências

- Depois de reexecutar o experimento ou o relatório, as figuras precisam ser geradas de novo (passo incluído no README).
- As medianas das features, os órgãos superiores e os testes de hipóteses completos continuam em tabela no relatório: são números de escalas diferentes ou listas, que ficam mais claros como tabela no artigo.
