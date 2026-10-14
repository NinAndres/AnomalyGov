# 0002 — Pseudonimização de pessoas físicas

- **Data:** 2026-10-14
- **Status:** aceita

## Contexto

Cerca de 71% das linhas de 2025-01 têm pessoa física como favorecido. O Portal já publica o CPF mascarado (`***.123.456-**`) junto com o nome completo. O CPF mascarado sozinho não identifica a pessoa: em 2025-01 há 318.662 códigos distintos para 387.563 combinações distintas de código e nome.

## Decisão

- O identificador do favorecido é `SHA-256(código + "|" + nome)` para pessoas físicas e `SHA-256(código)` para os demais tipos. É gravado em `favored.key_hash`.
- Para pessoas físicas, `favored.code` e `favored.name` ficam nulos (garantido por `CHECK` no banco). Nome e CPF mascarado não são armazenados.
- Para os demais tipos (empresas, órgãos, exterior), código e nome são mantidos para exibição.

## Consequências

- As features por favorecido (frequência, total recebido etc.) usam `favored_id` sem expor a identidade.
- Homônimos com os mesmos seis dígitos centrais do CPF seriam tratados como uma só pessoa. O risco é considerado desprezível.
- O hash não é uma anonimização: quem tiver o arquivo público do Portal consegue recalculá-lo. O objetivo é não armazenar nem exibir nomes e CPFs, não impedir a reidentificação a partir da fonte pública.
- Mudar a regra de normalização do nome muda os hashes, o que exige reingerir as bases.
