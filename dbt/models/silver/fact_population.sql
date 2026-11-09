-- Cifras oficiales de población (Padrón, 1 de enero). Una fila por territorio × año × sexo.
with ccaa as (
    select 'ES-CA-' || comunidades_y_ciudades_autonomas__cod as geo_id, 'ccaa' as geo_level,
           anyo, sexo, valor, tipo_dato, tabla, _execution_id
    from {{ bronze('INE-DPOP-CCAA', 'tabla_*') }}
    where tamano_de_los_municipios__cod = '0'
      and comunidades_y_ciudades_autonomas__cod not in ('00', '')
), nac as (
    select 'ES' as geo_id, 'nacional' as geo_level, anyo, sexo, valor, tipo_dato, tabla, _execution_id
    from {{ bronze('INE-DPOP-CCAA', 'tabla_*') }}
    where tamano_de_los_municipios__cod = '0' and comunidades_y_ciudades_autonomas__cod = '00'
), prov as (
    select 'ES-PR-' || provincias__cod as geo_id, 'provincia' as geo_level,
           anyo, sexo, valor, tipo_dato, tabla, _execution_id
    from {{ bronze('INE-DPOP-PROV', 'tabla_*') }}
    where provincias__cod is not null and provincias__cod <> ''
      and coalesce(tamano_de_los_municipios__cod, '0') = '0'
), mun as (
    select 'ES-MU-' || municipios__cod as geo_id, 'municipio' as geo_level,
           anyo, sexo, valor, tipo_dato, tabla, _execution_id
    from {{ bronze('INE-DPOP-MUN', 'tabla_*') }}
    where municipios__cod is not null and length(municipios__cod) = 5
      and coalesce(tamano_de_los_municipios__cod, '0') = '0'
)
select geo_id, geo_level, anyo,
       case sexo when 'Total' then 'T' when 'Hombres' then 'H' when 'Mujeres' then 'M' else sexo end as sexo,
       cast(valor as bigint) as poblacion, tipo_dato,
       'INE-DPOP' as source_family, tabla as tabla_ine, _execution_id
from (select * from nac union all select * from ccaa union all select * from prov union all select * from mun)
where valor is not null
