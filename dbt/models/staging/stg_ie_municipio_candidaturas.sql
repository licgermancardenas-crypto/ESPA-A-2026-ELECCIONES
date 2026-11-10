{{ config(enabled=var('has_infoelectoral')) }}
-- Fichero 06: votos por candidatura y municipio.
select
    tipo_eleccion || '-' || anno || mes as election_id,
    tipo_eleccion || '-' || anno || mes || '-' || codigo_candidatura as candidacy_id,
    codigo_provincia, codigo_municipio, codigo_distrito,
    codigo_provincia || codigo_municipio as municipio_ine,
    codigo_municipio = '999'             as es_cera,
    votos, escanos,
    _source_id, _execution_id
from {{ bronze('MIR-IE-*', 'f06_*') }}
where regexp_full_match(anno, '(19|20)\d\d')
