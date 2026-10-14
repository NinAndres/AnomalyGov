-- 003: amostras, execuções de algoritmos e escores (decisões 0005 e 0006).

CREATE TABLE samples (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source            text        NOT NULL,
    seed              integer     NOT NULL,
    total             integer     NOT NULL,
    floor             integer     NOT NULL,
    strata            text[]      NOT NULL,
    dataset_file_ids  integer[]   NOT NULL,
    population_size   integer     NOT NULL,
    sample_size       integer     NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, seed, total, floor, strata, dataset_file_ids)
);

CREATE TABLE sample_records (
    sample_id   integer          NOT NULL REFERENCES samples (id) ON DELETE CASCADE,
    payment_id  bigint           NOT NULL REFERENCES payments (id),
    weight      double precision NOT NULL CHECK (weight >= 1),
    PRIMARY KEY (sample_id, payment_id)
);

CREATE TABLE runs (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    experiment        text             NOT NULL,
    config_sha256     char(64)         NOT NULL,
    mode              text             NOT NULL CHECK (mode IN ('experiment', 'exploration')),
    purpose           text             NOT NULL CHECK (purpose IN
                      ('main', 'parameter', 'data_stability', 'scalability', 'artifact')),
    algorithm         text             NOT NULL CHECK (algorithm IN ('isolation_forest', 'lof', 'one_class_svm')),
    params            jsonb            NOT NULL,
    random_state      integer,
    feature_columns   text[]           NOT NULL,
    train_sample_id   integer          NOT NULL REFERENCES samples (id),
    scored_sample_id  integer          REFERENCES samples (id),
    n_train           integer          NOT NULL,
    n_scored          integer          NOT NULL,
    fit_seconds       double precision NOT NULL,
    score_seconds     double precision NOT NULL,
    environment       jsonb            NOT NULL,
    created_at        timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX runs_experiment_idx ON runs (experiment, purpose, algorithm);

-- Escores gravados apenas quando scored_sample_id não é nulo (a escalabilidade grava só tempos).
CREATE TABLE run_scores (
    run_id            integer          NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    payment_id        bigint           NOT NULL REFERENCES payments (id),
    raw_score         double precision NOT NULL,
    normalized_score  real             NOT NULL CHECK (normalized_score > 0 AND normalized_score <= 1),
    PRIMARY KEY (run_id, payment_id)
);
