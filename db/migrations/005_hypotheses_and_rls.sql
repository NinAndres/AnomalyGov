-- 005: execuções e resultados dos testes de hipóteses (decisão 0008) e RLS em todas as tabelas.

ALTER TABLE runs DROP CONSTRAINT runs_purpose_check;
ALTER TABLE runs ADD CONSTRAINT runs_purpose_check CHECK (purpose IN
    ('main', 'parameter', 'data_stability', 'scalability', 'artifact',
     'h1_cell', 'h1_subsample', 'h1_manipulation', 'h2_month', 'h2_noise'));

-- Subconjunto da amostra de treino usado pela execução (ex.: {"month": 3, "half": "A"}); nulo = amostra inteira.
ALTER TABLE runs ADD COLUMN subset jsonb;

-- Medidas por unidade de análise (célula mês × tipo na H1, par de meses na H2).
CREATE TABLE hypothesis_units (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    experiment  text        NOT NULL,
    hypothesis  text        NOT NULL,
    unit        jsonb       NOT NULL,
    measures    jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX hypothesis_units_experiment_idx ON hypothesis_units (experiment, hypothesis);

CREATE TABLE hypothesis_tests (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    experiment  text             NOT NULL,
    hypothesis  text             NOT NULL,
    family      text             NOT NULL,
    test        text             NOT NULL,
    variable    text             NOT NULL,
    n           integer          NOT NULL,
    statistic   double precision,
    effect      double precision,
    ci_low      double precision,
    ci_high     double precision,
    p_value     double precision,
    p_adjusted  double precision,
    details     jsonb            NOT NULL DEFAULT '{}',
    created_at  timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX hypothesis_tests_experiment_idx ON hypothesis_tests (experiment, hypothesis);

-- No Supabase, tabelas do schema public ficam expostas pela API REST (papéis anon e authenticated).
-- RLS ativo e sem políticas bloqueia esse acesso; o backend usa um papel que ignora RLS.
ALTER TABLE dataset_files     ENABLE ROW LEVEL SECURITY;
ALTER TABLE management_units  ENABLE ROW LEVEL SECURITY;
ALTER TABLE favored           ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments          ENABLE ROW LEVEL SECURITY;
ALTER TABLE samples           ENABLE ROW LEVEL SECURITY;
ALTER TABLE sample_records    ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_scores        ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_metrics       ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_comparisons   ENABLE ROW LEVEL SECURITY;
ALTER TABLE hypothesis_units  ENABLE ROW LEVEL SECURITY;
ALTER TABLE hypothesis_tests  ENABLE ROW LEVEL SECURITY;
