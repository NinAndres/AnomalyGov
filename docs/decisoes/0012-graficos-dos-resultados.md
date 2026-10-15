# 0012 — Gráficos dos resultados do experimento

- **Data:** 2026-10-15
- **Status:** aceita

## Contexto

A página do experimento mostrava os resultados só em tabelas, o que dificulta comparar os três algoritmos de relance. Além disso, parte dos resultados do relatório (características dos sinalizados, interpretabilidade e sobreposição entre algoritmos) existia apenas em `docs/resultados/<experimento>.md` e não chegava à aplicação.

## Decisões

- **Recharts 3** (`recharts` 3.10.1, com `react-is` 19.1.0 como dependência par) para os gráficos do frontend, versões fixadas no `package.json`. É uma exceção à decisão 0011, que evitava bibliotecas: os gráficos de barras, linhas e intervalos ficariam caros de manter em SVG próprio.
- **Toda tabela continua na página.** Cada gráfico tem a tabela correspondente logo abaixo (ou em um bloco expansível), que é o equivalente acessível e a fonte dos valores exatos.
- **Cores:** uma cor fixa por algoritmo (posições 1 a 3 de uma paleta categórica validada para daltonismo: Isolation Forest azul `#2a78d6`, LOF laranja `#eb6834`, One-Class SVM verde-água `#1baf7a`), a mesma em todos os gráficos e nos marcadores da tabela de registros. Séries ordenadas (`p`, número de algoritmos) usam uma rampa de um só tom de azul. Textos (eixos, legendas, rótulos) ficam em cinza ou preto, nunca na cor da série. O verde-água tem contraste abaixo de 3:1 com o fundo; as tabelas compensam isso.
- **Os números vêm do relatório, não são recalculados.** `anomalygov_ml.report` passa a gravar as características dos sinalizados, a árvore substituta e a sobreposição nas tabelas da migration 008 (`run_profiles`, `run_surrogates`, `experiment_overlaps`), e a publicação as copia para o Supabase. O backend só lê essas tabelas (`GET /api/experiments/{nome}`). Assim, a aplicação mostra exatamente os valores do artigo, e a lógica de cálculo continua só no Python.
- **Gráficos por seção:**

| Seção | Gráfico |
|---|---|
| Execução | Tempo total por algoritmo; proporção ponderada de sinalizados por `p` |
| Concordância | Jaccard por par de algoritmos e `p`; registros sinalizados por 1, 2 ou 3 algoritmos |
| Estabilidade | Jaccard frente aos dados (mediana, mínimo e máximo); Jaccard de cada variação de parâmetro |
| Escalabilidade | Tempo por tamanho da amostra, com eixos logarítmicos |
| Características | Taxa ponderada por tipo de favorecido e por mês; feature dominante. Medianas das features e órgãos superiores ficam em tabela (escalas diferentes) |
| Interpretabilidade | Fidelidade (R²) da árvore substituta; regras em blocos expansíveis |
| Hipóteses | H2: Jaccard mediano entre meses, com o ruído de semente do Isolation Forest como referência; H1c: retenção dos sinalizados por fração de cópias |

## Consequências

- O Supabase precisa da migration 008 antes de publicar o experimento novamente. As tabelas novas são pequenas: 510 linhas de características, 3 árvores e 9 contagens de sobreposição para `principal-2025`.
- O pacote do frontend passou de 500 kB minificado por causa do Recharts (o Vite avisa no build). Para o uso atual, isso é aceitável; se pesar, os gráficos podem ser carregados sob demanda.
- No jsdom (testes), os gráficos não têm tamanho e o Recharts só emite avisos. Os testes verificam os títulos dos gráficos e as tabelas.
