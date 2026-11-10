{{ config(enabled=var('has_infoelectoral')) }}
-- Resultados por agrupación oficial (código de acumulación nacional del Ministerio).
-- Nombre de la agrupación = sigla (y denominación) de su candidatura con más votos en la convocatoria.
with base as (
    select r.election_id, r.geo_level, r.geo_id, r.candidacy_id, r.votos, r.escanos,
           a.agrupacion_id, a.siglas, a.denominacion
    from {{ ref('fact_election_results') }} r
    join {{ ref('ie_agrupaciones') }} a on a.candidacy_id = r.candidacy_id
),
nombres as (
    select agrupacion_id, arg_max(siglas, v) as agrupacion_siglas, arg_max(denominacion, v) as agrupacion_denominacion
    from (select agrupacion_id, siglas, denominacion, sum(votos) as v from base
          where geo_level = 'municipio' group by all)
    group by agrupacion_id
),
g as (
    select b.election_id, b.geo_level, b.geo_id, b.agrupacion_id,
           coalesce(n.agrupacion_siglas, any_value(b.siglas)) as agrupacion_siglas,
           any_value(n.agrupacion_denominacion) as agrupacion_denominacion,
           sum(b.votos) as votos, sum(b.escanos) as escanos, count(distinct b.candidacy_id) as n_candidaturas
    from base b left join nombres n using (agrupacion_id)
    group by b.election_id, b.geo_level, b.geo_id, b.agrupacion_id, n.agrupacion_siglas
)
select *, votos::double / nullif(sum(votos) over (partition by election_id, geo_level, geo_id), 0) as vote_share
from g
