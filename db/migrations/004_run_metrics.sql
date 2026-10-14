-- 004: métricas por execução e comparações entre execuções (decisão 0007).

CREATE TABLE run_metrics (
    run_id                  integer          NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    p                       numeric(4, 3)    NOT NULL CHECK (p > 0 AND p < 1),
    flagged_count           integer          NOT NULL,
    flagged_share           double precision NOT NULL,
    weighted_flagged_share  double precision NOT NULL,
    PRIMARY KEY (run_id, p)
);

-- Pares sempre gravados com run_a < run_b. Ambas as execuções pontuam a mesma amostra.
CREATE TABLE run_comparisons (
    run_a     integer          NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    run_b     integer          NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    p         numeric(4, 3)    NOT NULL CHECK (p > 0 AND p < 1),
    jaccard   double precision NOT NULL,
    spearman  double precision NOT NULL,
    PRIMARY KEY (run_a, run_b, p),
    CHECK (run_a < run_b)
);
