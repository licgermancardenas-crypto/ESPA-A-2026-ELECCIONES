{{ config(enabled=var('has_infoelectoral')) }}
-- Índices por convocatoria y territorio. Fórmulas (ver docs/METHODOLOGY.md):
--   ENEP = 1/Σ v_i²   ENPP = 1/Σ s_i²   (Laakso–Taagepera)
--   Gallagher = sqrt(½ Σ (v_i − s_i)²) en puntos %   (solo con escaños asignados en ese nivel)
--   margen = (v_1 − v_2), competitividad = 1 − margen, dominio = v_1
--   votos_sin_escano = votos de candidaturas con 0 escaños (solo niveles con escaños)
with r as (select * from {{ ref('fact_election_results') }}),
seats as (
    select election_id, geo_level, geo_id, sum(escanos) as total_escanos
    from r group by all
),
s as (
    select r.*, r.escanos::double / nullif(st.total_escanos, 0) as seat_share, st.total_escanos
    from r join seats st using (election_id, geo_level, geo_id)
)
select
    election_id, geo_level, geo_id,
    count(*) filter (where votos > 0)                       as n_candidaturas,
    sum(votos)                                              as votos_candidaturas,
    any_value(total_escanos)                                as escanos,
    1 / nullif(sum(vote_share * vote_share), 0)             as enep,
    case when any_value(total_escanos) > 0
         then 1 / nullif(sum(seat_share * seat_share), 0) end as enpp,
    case when any_value(total_escanos) > 0
         then sqrt(0.5 * sum(power(100 * vote_share - 100 * coalesce(seat_share, 0), 2))) end as gallagher,
    max(vote_share) filter (where rank_votos = 1)           as dominio,
    max(vote_share) filter (where rank_votos = 1)
      - coalesce(max(vote_share) filter (where rank_votos = 2), 0) as margen,
    1 - (max(vote_share) filter (where rank_votos = 1)
      - coalesce(max(vote_share) filter (where rank_votos = 2), 0)) as competitividad,
    arg_max(siglas, votos)                                  as ganador_siglas,
    case when any_value(total_escanos) > 0
         then sum(votos) filter (where coalesce(escanos, 0) = 0) end as votos_sin_escano
from s
group by election_id, geo_level, geo_id
