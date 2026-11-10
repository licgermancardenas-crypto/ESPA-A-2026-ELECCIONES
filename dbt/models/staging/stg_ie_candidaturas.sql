{{ config(enabled=var('has_infoelectoral')) }}
-- Fichero 03: candidaturas por convocatoria (códigos propios de cada elección).
select distinct
    tipo_eleccion || '-' || anno || mes                 as election_id,
    tipo_eleccion, anno, mes,
    tipo_eleccion || '-' || anno || mes || '-' || codigo_candidatura as candidacy_id,
    codigo_candidatura,
    siglas,
    denominacion,
    nullif(codigo_candidatura_provincial, '000000') as codigo_candidatura_provincial,
    nullif(codigo_candidatura_autonomica, '000000') as codigo_candidatura_autonomica,
    nullif(codigo_candidatura_nacional, '000000')   as codigo_candidatura_nacional,
    _source_id, _execution_id
from {{ bronze('MIR-IE-*', 'f03_*') }}
where regexp_full_match(anno, '(19|20)\d\d')
