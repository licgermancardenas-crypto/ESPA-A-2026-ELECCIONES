{{ config(enabled=var('has_infoelectoral')) }}
-- Resultados por agrupación oficial (código de acumulación nacional del Ministerio).
with g as (
    select r.election_id, r.geo_level, r.geo_id, a.agrupacion_id, a.agrupacion_siglas,
           sum(r.votos) as votos, sum(r.escanos) as escanos, count(distinct r.candidacy_id) as n_candidaturas
    from {{ ref('fact_election_results') }} r
    join {{ ref('ie_agrupaciones') }} a on a.candidacy_id = r.candidacy_id
    group by r.election_id, r.geo_level, r.geo_id, a.agrupacion_id, a.agrupacion_siglas
)
select *, votos::double / nullif(sum(votos) over (partition by election_id, geo_level, geo_id), 0) as vote_share
from g
