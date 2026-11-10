{{ config(enabled=var('has_infoelectoral')) }}
-- Agrupación OFICIAL de candidaturas: código de acumulación nacional del fichero 03
-- (p. ej. PSC, PSdeG-PSOE, PSE-EE → PSOE; listas territoriales de SUMAR → SUMAR).
-- El nombre de la agrupación se asigna en gold.results_by_group (sigla con más votos).
select candidacy_id, election_id, siglas, denominacion,
       coalesce(codigo_candidatura_nacional, codigo_candidatura) as agrupacion_cod,
       election_id || '-' || coalesce(codigo_candidatura_nacional, codigo_candidatura) as agrupacion_id
from {{ ref('stg_ie_candidaturas') }}
