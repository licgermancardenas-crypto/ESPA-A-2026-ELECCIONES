{{ config(enabled=var('has_infoelectoral')) }}
-- Votos y escaños por candidatura y territorio. vote_share sobre votos a candidaturas;
-- share_valid sobre votos válidos (candidaturas + blancos), base de la barrera legal.
with mun as (
    select c.election_id, 'municipio' as geo_level, 'ES-MU-' || c.municipio_ine as geo_id,
           c.candidacy_id, c.votos, c.escanos
    from {{ ref('stg_ie_municipio_candidaturas') }} c
    where c.codigo_distrito = '99' and not c.es_cera
), sup as (
    select s.election_id, s.nivel,
           case s.nivel when 'nacional' then 'ES'
                        when 'ccaa' then 'ES-CA-' || x.ccaa_ine
                        when 'provincia' then 'ES-PR-' || s.codigo_provincia
                        else 'ES-PR-' || s.codigo_provincia || '-D' || s.codigo_distrito_electoral end,
           s.candidacy_id, s.votos, s.escanos
    from {{ ref('stg_ie_superior_candidaturas') }} s
    left join {{ ref('xw_ccaa_mir_ine') }} x
           on x.election_id = s.election_id and x.codigo_ccaa_mir = s.codigo_ccaa_mir
), r as (select * from mun union all select * from sup)
select r.*,
       k.siglas, k.denominacion,
       r.votos::double / nullif(sum(r.votos) over w, 0)                    as vote_share,
       r.votos::double / nullif(t.votos_validos, 0)                         as share_valid,
       rank() over (partition by r.election_id, r.geo_level, r.geo_id order by r.votos desc) as rank_votos
from r
left join {{ ref('stg_ie_candidaturas') }} k on k.candidacy_id = r.candidacy_id
left join {{ ref('fact_turnout') }} t
       on t.election_id = r.election_id and t.geo_level = r.geo_level and t.geo_id = r.geo_id
window w as (partition by r.election_id, r.geo_level, r.geo_id)
