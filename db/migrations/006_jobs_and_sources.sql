-- 006: definição das bases para a interface, fila de jobs do modo exploration e view de exibição (decisão 0009).

-- Definição declarativa de cada base (adaptador), gravada pela publicação. O backend a lê para validar
-- filtros e o frontend monta a tela de filtros a partir dela.
CREATE TABLE sources (
    name             text        PRIMARY KEY,
    label            text        NOT NULL,
    filters          jsonb       NOT NULL,  -- [{name, type, label, options?: [{value, label}], min?, max?}]
    display_columns  jsonb       NOT NULL,  -- ["reference_month", ...]
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    source       text        NOT NULL REFERENCES sources (name),
    mode         text        NOT NULL DEFAULT 'exploration' CHECK (mode = 'exploration'),
    status       text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    filters      jsonb       NOT NULL DEFAULT '{}',
    params       jsonb       NOT NULL DEFAULT '{}',
    result       jsonb,      -- resumo gravado pelo worker ao concluir (ver docs/contratos.md)
    error        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    started_at   timestamptz,
    finished_at  timestamptz,
    CHECK ((status = 'pending') = (started_at IS NULL)),
    CHECK ((status IN ('succeeded', 'failed')) = (finished_at IS NOT NULL)),
    CHECK ((status = 'failed') = (error IS NOT NULL))
);

-- O worker reserva o job pendente mais antigo com SELECT ... FOR UPDATE SKIP LOCKED.
CREATE INDEX jobs_pending_idx ON jobs (created_at) WHERE status = 'pending';

ALTER TABLE runs ADD COLUMN job_id uuid REFERENCES jobs (id) ON DELETE CASCADE;
CREATE INDEX runs_job_id_idx ON runs (job_id) WHERE job_id IS NOT NULL;

-- Colunas de exibição da base de pagamentos. Nome e código de pessoa física nunca aparecem (LGPD),
-- mesmo que estejam preenchidos por engano. security_invoker faz a view respeitar o RLS de quem consulta.
CREATE VIEW payments_display WITH (security_invoker = true) AS
SELECT p.id,
       to_char(p.reference_month, 'YYYY-MM')                                   AS reference_month,
       f.favored_type,
       CASE WHEN f.favored_type = 'individual' THEN NULL ELSE f.name END        AS favored_name,
       CASE WHEN f.favored_type = 'individual' THEN NULL ELSE f.code END        AS favored_code,
       m.superior_agency_code,
       m.superior_agency_name,
       p.management_unit_code,
       m.name                                                                  AS management_unit_name,
       p.uf,
       p.municipality,
       p.amount
FROM payments p
JOIN favored f ON f.id = p.favored_id
JOIN management_units m ON m.code = p.management_unit_code;

ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs    ENABLE ROW LEVEL SECURITY;
