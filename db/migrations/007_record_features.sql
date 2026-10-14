-- 007: features dos registros publicados, usadas pelo worker do modo exploration (decisão 0010).
-- As features dependem do ano inteiro (decisão 0005), que só existe no banco local; a publicação grava
-- os valores já calculados para os registros da amostra.

ALTER TABLE sources ADD COLUMN feature_columns jsonb NOT NULL DEFAULT '[]';

CREATE TABLE record_features (
    source     text               NOT NULL REFERENCES sources (name) ON DELETE CASCADE,
    record_id  bigint             NOT NULL,
    "values"   double precision[] NOT NULL,  -- na ordem de sources.feature_columns
    PRIMARY KEY (source, record_id)
);

ALTER TABLE record_features ENABLE ROW LEVEL SECURITY;
