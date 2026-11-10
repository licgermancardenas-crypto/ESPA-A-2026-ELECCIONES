{{ config(enabled=var('has_euskadi') or var('has_cmadrid')) }}
-- Resultados autonómicos publicados por las comunidades: Open Data Euskadi (Parlamento Vasco 1980–2024,
-- Congreso 2023 en la CAPV) y Datos Abiertos Comunidad de Madrid (Asamblea 1991–2023).
-- Separado de fact_election_results (Infoelectoral) para no mezclar fuentes ni codificaciones.
-- mesa: geo_id = ES-ME-{municipio}{distrito}{seccion 3d}{mesa}
with b as (
    {% if var('has_euskadi') %}select * from {{ bronze('EUSKADI-ELEC', '*') }}{% endif %}
    {% if var('has_euskadi') and var('has_cmadrid') %}union all by name{% endif %}
    {% if var('has_cmadrid') %}select * from {{ bronze('CMADRID-ELEC', '*') }}{% endif %}
)
select
    coalesce(election_key, 'EUS-' || convocatoria)          as election_id,
    tipo, cast(anyo as int) as anyo, nivel,
    case nivel when 'territorio' then 'ES-PR-' || provincia_ine
               when 'municipio' then 'ES-MU-' || municipio_ine
               else 'ES-ME-' || municipio_ine || lpad(distrito, 2, '0') || lpad(seccion, 3, '0') || mesa end as geo_id,
    case when nivel = 'mesa' then 'ES-SE-' || municipio_ine || lpad(distrito, 2, '0') || lpad(seccion, 3, '0') end as seccion_geo_id,
    provincia_ine, municipio_ine,
    candidatura, try_cast(votos as double)::bigint as votos, try_cast(escanos as double)::int as escanos,
    try_cast(censo as double)::bigint as censo, try_cast(votantes as double)::bigint as votantes,
    try_cast(nulos as double)::bigint as nulos, try_cast(blancos as double)::bigint as blancos,
    try_cast(validos as double)::bigint as validos, try_cast(votos_candidaturas as double)::bigint as votos_candidaturas,
    _execution_id
from b
where candidatura is not null
