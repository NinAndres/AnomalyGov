-- 002: registra as linhas excluídas na ingestão (fora do escopo do projeto).
-- row_count continua sendo o total de linhas do arquivo bruto.

ALTER TABLE dataset_files
    ADD COLUMN loaded_row_count integer,
    ADD COLUMN excluded_rows    jsonb NOT NULL DEFAULT '{}';

-- Arquivos ingeridos antes desta migration não tiveram exclusões.
UPDATE dataset_files SET loaded_row_count = row_count;

ALTER TABLE dataset_files
    ALTER COLUMN loaded_row_count SET NOT NULL,
    ADD CHECK (loaded_row_count >= 0 AND loaded_row_count <= row_count);
