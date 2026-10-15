-- 008: características dos sinalizados, interpretabilidade e sobreposição entre algoritmos (decisão 0007).
-- Calculadas por anomalygov_ml.report para as execuções principais e copiadas pela publicação, para que a
-- aplicação mostre os mesmos números do relatório em docs/resultados/.

-- Uma linha por execução principal, limiar, dimensão e categoria. O significado de value e baseline depende
-- da dimensão:
--   favored_type, reference_month: value = taxa ponderada de sinalização no grupo;
--                                  baseline = participação ponderada do grupo na população.
--   superior_agency:               value = participação ponderada do órgão entre os sinalizados;
--                                  baseline = participação ponderada do órgão na população.
--   feature_median:                value = mediana entre os sinalizados; baseline = mediana na amostra
--                                  (categoria = nome da feature, ou 'amount' para o valor em R$).
--   dominant_feature:              value = proporção dos sinalizados cuja feature dominante é a categoria;
--                                  baseline nula.
CREATE TABLE run_profiles (
    run_id     integer          NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    p          numeric(4, 3)    NOT NULL CHECK (p > 0 AND p < 1),
    dimension  text             NOT NULL CHECK (dimension IN ('favored_type', 'reference_month', 'superior_agency',
                                                              'feature_median', 'dominant_feature')),
    category   text             NOT NULL,
    value      double precision NOT NULL,
    baseline   double precision,
    PRIMARY KEY (run_id, p, dimension, category)
);

-- Substituto global (árvore de regressão rasa que imita o escore normalizado): fidelidade R² e regras.
CREATE TABLE run_surrogates (
    run_id    integer          PRIMARY KEY REFERENCES runs (id) ON DELETE CASCADE,
    depth     integer          NOT NULL,
    fidelity  double precision NOT NULL,
    rules     text             NOT NULL
);

-- Registros da amostra principal sinalizados por exatamente algorithm_count algoritmos, por limiar.
CREATE TABLE experiment_overlaps (
    experiment       text          NOT NULL,
    p                numeric(4, 3) NOT NULL CHECK (p > 0 AND p < 1),
    algorithm_count  integer       NOT NULL CHECK (algorithm_count > 0),
    record_count     integer       NOT NULL,
    PRIMARY KEY (experiment, p, algorithm_count)
);

ALTER TABLE run_profiles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_surrogates       ENABLE ROW LEVEL SECURITY;
ALTER TABLE experiment_overlaps  ENABLE ROW LEVEL SECURITY;
