-- GEOGRAPHIC MASTER REGISTRY (atributos). Geometrías en gold.geo_boundaries.
-- geo_id canónico derivado del código oficial INE, nunca del nombre.
select 'ES' as geo_id, 'pais' as geo_type, 'España' as geo_name, null as parent_geo_id,
       'ES' as official_code, null::date as valid_from, null::date as valid_to, 'INE-DPOP-CCAA' as source_id
union all
select geo_id, 'ccaa', nombre, 'ES', ccaa_ine, null, null, 'INE-DPOP-CCAA' from {{ ref('ref_ccaa') }}
union all
select geo_id, 'provincia', nombre, parent_geo_id, provincia_ine, null, null, 'INE-DPOP-PROV' from {{ ref('ref_provincia') }}
union all
select geo_id, 'municipio', nombre, parent_geo_id, municipio_ine,
       case when existia_antes_de_cobertura then null else valid_from_observado end,
       valid_to, 'INE-CODMUN'
from {{ ref('dim_municipality') }}
{% if var('has_seccionado') %}
union all
select geo_id, geo_type, geo_name, parent_geo_id, official_code, valid_from, valid_to, source_id
from silver.geo_census_units
{% endif %}
