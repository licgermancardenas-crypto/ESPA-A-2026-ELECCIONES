{{ config(enabled=var('has_infoelectoral')) }}
-- Ficheros 07/08: ámbitos superiores al municipio.
-- codigo_ccaa_mir '99' = total nacional; codigo_provincia '99' = total de la comunidad;
-- codigo_distrito_electoral '9' = total de la provincia (otros valores: islas/distritos).
select
    t.tipo_eleccion || '-' || t.anno || t.mes as election_id,
    t.tipo_eleccion, t.anno, t.mes,
    t.codigo_ccaa_mir, t.codigo_provincia, t.codigo_distrito_electoral,
    case when t.codigo_ccaa_mir = '99' then 'nacional'
         when t.codigo_provincia = '99' then 'ccaa'
         when t.codigo_distrito_electoral = '9' then 'provincia'
         else 'distrito_electoral' end as nivel,
    t.nombre_ambito,
    t.poblacion_derecho, t.numero_mesas, t.censo_ine, t.censo_escrutinio, t.censo_cere, t.votantes_cere,
    t.votos_blancos, t.votos_nulos, t.votos_candidaturas,
    t.votos_blancos + t.votos_nulos + t.votos_candidaturas as votantes,
    t.votos_blancos + t.votos_candidaturas                 as votos_validos,
    t.numero_escanos, t.votos_afirmativos, t.votos_negativos, t.datos_oficiales,
    t._source_id, t._execution_id
from {{ bronze('MIR-IE-*', 'f07_*') }} t
where regexp_full_match(anno, '(19|20)\d\d')
