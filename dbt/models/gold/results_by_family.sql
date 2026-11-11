{{ config(enabled=var('has_infoelectoral')) }}
-- Familias políticas para comparar convocatorias (party_family_map: tabla manual + reglas de nombre).
-- Reglas: se agrupan solo siglas listadas explícitamente para cada convocatoria; las coaliciones
-- mixtas (Ahora Repúblicas, CEUS, NA+) son una familia propia; lo no listado queda como "Otros".
-- Sumar (2023) y Podemos y confluencias (2015-2019) son familias DISTINTAS: no se asume continuidad.
with g as (
    select r.*, coalesce(f.familia, 'Otros') as familia
    from {{ ref('results_by_group') }} r
    left join {{ ref('party_family_map') }} f
           on f.election_id = r.election_id and f.agrupacion_siglas = r.agrupacion_siglas
)
, a as (
    select election_id, geo_level, geo_id, familia, sum(votos) as votos, sum(escanos) as escanos
    from g group by election_id, geo_level, geo_id, familia
)
select *, votos::double / nullif(sum(votos) over (partition by election_id, geo_level, geo_id), 0) as vote_share
from a
