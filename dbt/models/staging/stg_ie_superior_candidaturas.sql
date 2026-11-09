{{ config(enabled=var('has_infoelectoral')) }}
select
    tipo_eleccion || '-' || anno || mes as election_id,
    tipo_eleccion || '-' || anno || mes || '-' || codigo_candidatura as candidacy_id,
    codigo_ccaa_mir, codigo_provincia, codigo_distrito_electoral,
    case when codigo_ccaa_mir = '99' then 'nacional'
         when codigo_provincia = '99' then 'ccaa'
         when codigo_distrito_electoral = '9' then 'provincia'
         else 'distrito_electoral' end as nivel,
    votos, escanos,
    _source_id, _execution_id
from {{ bronze('MIR-IE-*', 'f08_*') }}
