-- PIB y PIB per cápita (Contabilidad Regional, INE) por provincia y CCAA.
select
    case when provincias__cod is not null and provincias__cod <> '' then 'ES-PR-' || provincias__cod
         when comunidades_y_ciudades_autonomas__cod is not null and comunidades_y_ciudades_autonomas__cod <> ''
              then 'ES-CA-' || comunidades_y_ciudades_autonomas__cod
         else 'ES' end                         as geo_id,
    anyo,
    saldos_contables                           as indicador,
    tipo_de_dato                               as tipo,
    precios_sec                                as precios,
    unidad, escala, tipo_dato                  as estado_dato,
    valor, tabla as tabla_ine, _execution_id
from {{ bronze('INE-CRE-PIB', 'tabla_*') }}
where valor is not null
