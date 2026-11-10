{{ config(enabled=var('has_infoelectoral')) }}
-- Agrupación OFICIAL de candidaturas: código de acumulación nacional del fichero 03
-- (p. ej. PSC, PSdeG-PSOE, PSE-EE → PSOE; listas territoriales de SUMAR → SUMAR).
-- No es una regla de ATLAS: la asigna el Ministerio del Interior en cada convocatoria.
with k as (select * from {{ ref('stg_ie_candidaturas') }})
select k.candidacy_id, k.election_id, k.siglas, k.denominacion,
       coalesce(k.codigo_candidatura_nacional, k.codigo_candidatura)            as agrupacion_cod,
       k.election_id || '-' || coalesce(k.codigo_candidatura_nacional, k.codigo_candidatura) as agrupacion_id,
       coalesce(n.siglas, k.siglas)                                             as agrupacion_siglas
from k
left join k n on n.election_id = k.election_id and n.codigo_candidatura = k.codigo_candidatura_nacional
qualify row_number() over (partition by k.candidacy_id order by n.siglas nulls last) = 1
