-- Comunidades y ciudades autónomas con código INE (tabla Tempus 2853).
-- OJO: el Ministerio del Interior usa otra numeración de CCAA; nunca cruzar por ese código.
select distinct
    comunidades_y_ciudades_autonomas__cod                 as ccaa_ine,
    'ES-CA-' || comunidades_y_ciudades_autonomas__cod     as geo_id,
    trim(regexp_replace(comunidades_y_ciudades_autonomas, '^\d+\s+', '')) as nombre
from {{ bronze('INE-DPOP-CCAA', 'tabla_*') }}
where comunidades_y_ciudades_autonomas__cod not in ('00', '')
  and comunidades_y_ciudades_autonomas__cod is not null
