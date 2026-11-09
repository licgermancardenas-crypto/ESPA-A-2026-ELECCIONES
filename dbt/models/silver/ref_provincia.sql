-- Provincias (tabla 2852) con su comunidad según el diccionario de municipios vigente.
with prov as (
    select distinct provincias__cod as provincia_ine,
           trim(regexp_replace(provincias, '^\d+\s+', '')) as nombre
    from {{ bronze('INE-DPOP-PROV', 'tabla_*') }}
    where provincias__cod is not null and provincias__cod <> ''
),
ccaa as (
    select distinct CPRO as provincia_ine, CODAUTO as ccaa_ine
    from {{ bronze('INE-CODMUN', 'diccionario_*') }}
    where anyo_referencia = (select max(anyo_referencia) from {{ bronze('INE-CODMUN', 'diccionario_*') }})
)
select p.provincia_ine,
       'ES-PR-' || p.provincia_ine as geo_id,
       p.nombre,
       c.ccaa_ine,
       'ES-CA-' || c.ccaa_ine      as parent_geo_id
from prov p left join ccaa c using (provincia_ine)
