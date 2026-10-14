-- 001: tabelas de ingestão da base "Recebimentos de Recursos por Favorecido".

CREATE TABLE dataset_files (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source        text        NOT NULL,
    file_name     text        NOT NULL,
    sha256        char(64)    NOT NULL UNIQUE,
    row_count     integer     NOT NULL CHECK (row_count >= 0),
    period_start  date        NOT NULL,
    period_end    date        NOT NULL,
    ingested_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (period_end >= period_start)
);

CREATE TABLE management_units (
    code                  varchar(6) PRIMARY KEY,
    name                  text NOT NULL,
    agency_code           varchar(5) NOT NULL,
    agency_name           text NOT NULL,
    superior_agency_code  varchar(5) NOT NULL,
    superior_agency_name  text NOT NULL
);

-- Pessoas físicas: code e name ficam nulos (LGPD); a identidade é só key_hash.
CREATE TABLE favored (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key_hash      bytea NOT NULL UNIQUE,
    favored_type  text  NOT NULL CHECK (favored_type IN
                  ('individual', 'company', 'management_unit', 'foreign', 'special', 'other')),
    code          text,
    name          text,
    CHECK (favored_type <> 'individual' OR (code IS NULL AND name IS NULL))
);

-- Granularidade: total recebido por favorecido, unidade gestora, localidade e mês.
CREATE TABLE payments (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_file_id       integer       NOT NULL REFERENCES dataset_files (id),
    reference_month       date          NOT NULL,
    favored_id            bigint        NOT NULL REFERENCES favored (id),
    management_unit_code  varchar(6)    NOT NULL REFERENCES management_units (code),
    uf                    char(2),
    municipality          text,
    amount                numeric(18, 2) NOT NULL
);

CREATE INDEX payments_reference_month_idx ON payments (reference_month);
CREATE INDEX payments_favored_id_idx ON payments (favored_id);
CREATE INDEX payments_dataset_file_id_idx ON payments (dataset_file_id);
