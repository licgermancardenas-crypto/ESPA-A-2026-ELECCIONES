{{ config(enabled=var('has_infoelectoral')) }}
-- Participación y composición del voto por territorio.
-- Municipio: fichero 05 (total municipal, distrito 99, sin CERA).
-- Provincia/CCAA/nacional: fichero 07 (incluye CERA). La suma de municipios NO
-- coincide con la provincia por el voto CERA: se documenta, no se fuerza.
with mun as (
    select election_id, 'municipio' as geo_level, 'ES-MU-' || municipio_ine as geo_id,
           censo_escrutinio as censo, votantes, votos_validos, votos_blancos, votos_nulos,
           votos_candidaturas, numero_escanos, numero_mesas, false as incluye_cera, _source_id
    from {{ ref('stg_ie_municipios') }}
    where codigo_distrito = '99' and not es_cera
), sup as (
    select s.election_id, s.nivel as geo_level,
           case s.nivel when 'nacional' then 'ES'
                        when 'ccaa' then 'ES-CA-' || x.ccaa_ine
                        when 'provincia' then 'ES-PR-' || s.codigo_provincia
                        else 'ES-PR-' || s.codigo_provincia || '-D' || s.codigo_distrito_electoral end as geo_id,
           s.censo_escrutinio + coalesce(s.censo_cere, 0) as censo,
           s.votantes, s.votos_validos, s.votos_blancos, s.votos_nulos, s.votos_candidaturas,
           s.numero_escanos, s.numero_mesas, true as incluye_cera, s._source_id
    from {{ ref('stg_ie_superior') }} s
    left join {{ ref('xw_ccaa_mir_ine') }} x
           on x.election_id = s.election_id and x.codigo_ccaa_mir = s.codigo_ccaa_mir
)
select *,
       votantes::double / nullif(censo, 0)          as turnout,
       votos_blancos::double / nullif(votos_validos, 0) as blank_share,
       votos_nulos::double / nullif(votantes, 0)    as null_share
from (select * from mun union all select * from sup)
