-- PIB y PIB per cápita (Contabilidad Regional, INE) por provincia, CCAA y total.
-- Las comunidades uniprovinciales (Madrid, Asturias, Cantabria, Navarra, La Rioja,
-- Murcia, Baleares, Ceuta, Melilla) solo se publican como CCAA: su fila provincial
-- se DERIVA de la autonómica y se marca con derivado_uniprovincial = true.
with base as (
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
),
uniprov as (
    select parent_geo_id as ccaa_geo_id, any_value(geo_id) as prov_geo_id
    from {{ ref('ref_provincia') }} group by 1 having count(*) = 1
)
select *, false as derivado_uniprovincial from base
union all
select u.prov_geo_id, b.anyo, b.indicador, b.tipo, b.precios, b.unidad, b.escala, b.estado_dato,
       b.valor, b.tabla_ine, b._execution_id, true
from base b join uniprov u on u.ccaa_geo_id = b.geo_id
where not exists (select 1 from base p where p.geo_id = u.prov_geo_id and p.anyo = b.anyo
                  and p.indicador = b.indicador and p.tipo = b.tipo)
