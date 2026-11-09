-- Censo electoral de votación (INE — Oficina del Censo Electoral, tabla 80107).
-- La tabla publica SOLO el último proceso electoral (en la descarga de nov-2026:
-- autonómicas de Andalucía, periodo 2026M05). Filas sin valor se descartan.
select
    case when municipios__cod is not null then 'ES-MU-' || municipios__cod
         when provincias__cod is not null then 'ES-PR-' || provincias__cod
         when comunidades_y_ciudades_autonomas__cod is not null then 'ES-CA-' || comunidades_y_ciudades_autonomas__cod
         else 'ES' end                                         as geo_id,
    case when municipios__cod is not null then 'municipio'
         when provincias__cod is not null then 'provincia'
         when comunidades_y_ciudades_autonomas__cod is not null then 'ccaa'
         else 'nacional' end                                   as geo_level,
    tipo_de_eleccion                                           as tipo_eleccion,
    case when tipo_de_elector like '%(CERA)%' then 'CERA'
         when tipo_de_elector like '%(CERE)%' then 'CERE'
         when tipo_de_elector like '%(CER)%' then 'CER' end    as tipo_elector,
    case when dato like '%votaci%' then 'censo_votacion' else 'renuncia_propaganda' end as dato,
    periodo,
    cast(valor as bigint)                                      as electores,
    _execution_id
from {{ bronze('INE-OCE', 'tabla_*') }}
where valor is not null
