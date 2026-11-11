{{ config(materialized='table') }}
-- Mapa único candidatura → familia política.
-- 1) seeds/party_families.csv (revisión manual, prioridad);
-- 2) seeds/party_families_extra.csv (reglas de nombre de atlas_spain.electoral.familias_regionales, solo para
--    candidaturas que no figuran en la tabla manual: variantes de siglas y partidos regionales).
select election_id, agrupacion_siglas, familia, 'manual' as origen, null::varchar as regla
from {{ ref('party_families') }}
union all
select x.election_id, x.agrupacion_siglas, x.familia, 'regla' as origen, x.regla
from {{ ref('party_families_extra') }} x
where not exists (select 1 from {{ ref('party_families') }} m
                  where m.election_id = x.election_id and m.agrupacion_siglas = x.agrupacion_siglas)
