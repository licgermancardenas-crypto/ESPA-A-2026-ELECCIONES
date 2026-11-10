{{ config(enabled=var('has_infoelectoral')) }}
-- Fichero 05: datos comunes por municipio. codigo_distrito '99' = total municipal.
-- codigo_municipio '999' = CERA (residentes ausentes) agregado por provincia.
select
    tipo_eleccion || '-' || anno || mes as election_id,
    tipo_eleccion, anno, mes, vuelta,
    codigo_ccaa_mir,                     -- código CCAA del Ministerio (NO coincide con el INE)
    codigo_provincia,
    codigo_municipio,
    codigo_distrito,
    codigo_provincia || codigo_municipio as municipio_ine,
    codigo_municipio = '999'             as es_cera,
    nombre_municipio,
    poblacion_derecho, numero_mesas,
    censo_ine, censo_escrutinio, censo_cere, votantes_cere,
    votos_blancos, votos_nulos, votos_candidaturas,
    votos_blancos + votos_nulos + votos_candidaturas as votantes,
    votos_blancos + votos_candidaturas              as votos_validos,
    numero_escanos,
    datos_oficiales,
    nivel_zip, _zip, _source_id, _execution_id
from {{ bronze('MIR-IE-*', 'f05_*') }}
where regexp_full_match(anno, '(19|20)\d\d')
