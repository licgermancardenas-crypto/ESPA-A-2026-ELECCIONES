{{ config(enabled=var('has_euskadi')) }}
select election_id, tipo, anyo, nivel, geo_id, seccion_geo_id, provincia_ine, municipio_ine,
       any_value(censo) censo, any_value(votantes) votantes, any_value(nulos) nulos, any_value(blancos) blancos,
       any_value(validos) validos, any_value(votos_candidaturas) votos_candidaturas,
       any_value(votantes)::double / nullif(any_value(censo), 0) as turnout,
       sum(votos) as suma_votos_partidos,
       arg_max(candidatura, votos) as ganador,
       max(votos)::double / nullif(sum(votos), 0) as cuota_ganador
from {{ ref('fact_regional_results') }}
group by all
