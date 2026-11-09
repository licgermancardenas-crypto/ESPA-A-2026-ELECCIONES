{{ config(enabled=var('has_infoelectoral')) }}
select distinct
    s.election_id,
    s.tipo_eleccion,
    case s.tipo_eleccion when '01' then 'referendum' when '02' then 'congreso' when '03' then 'senado'
         when '04' then 'municipales' when '06' then 'cabildos' when '07' then 'europeas' end as election_type,
    cast(s.anno as int) as anno, cast(s.mes as int) as mes,
    try_cast(d.fecha as date) as fecha,
    s._source_id as source_id
from {{ ref('stg_ie_superior') }} s
left join {{ ref('election_dates') }} d on d.election_id = s.election_id
