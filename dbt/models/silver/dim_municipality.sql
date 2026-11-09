-- Municipios con vigencia derivada de los diccionarios anuales del INE (a 1 de enero).
-- valid_to nulo = existe en el último diccionario descargado.
-- Cobertura temporal limitada a los diccionarios ingeridos (ver ops.executions).
with d as (
    select CPRO || CMUN as municipio_ine, CPRO as provincia_ine, CODAUTO as ccaa_ine,
           DC as digito_control, NOMBRE as nombre, anyo_referencia
    from {{ bronze('INE-CODMUN', 'diccionario_*') }}
),
bounds as (select min(anyo_referencia) as y0, max(anyo_referencia) as y1 from d)
select
    municipio_ine,
    'ES-MU-' || municipio_ine                      as geo_id,
    arg_max(nombre, anyo_referencia)               as nombre,
    arg_max(provincia_ine, anyo_referencia)        as provincia_ine,
    'ES-PR-' || arg_max(provincia_ine, anyo_referencia) as parent_geo_id,
    arg_max(ccaa_ine, anyo_referencia)             as ccaa_ine,
    arg_max(digito_control, anyo_referencia)       as digito_control,
    make_date(min(anyo_referencia), 1, 1)          as valid_from_observado,
    case when max(anyo_referencia) < (select y1 from bounds)
         then make_date(max(anyo_referencia) + 1, 1, 1) end as valid_to,
    min(anyo_referencia) = (select y0 from bounds) as existia_antes_de_cobertura,
    count(distinct nombre)                         as n_denominaciones
from d
group by municipio_ine
