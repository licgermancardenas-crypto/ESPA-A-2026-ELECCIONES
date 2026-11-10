{{ config(enabled=var('has_infoelectoral')) }}
-- Panel analítico de Statistical Intelligence (formato largo).
-- Una fila = territorio × variable × categoría × período. No copia datos nuevos: reorganiza
-- tablas gold existentes. Las definiciones de cada variable están en el seed stat_variables.
-- Geografía: la VIGENTE (dim_geography 2024). Los códigos municipales históricos que ya no existen
-- (fusiones/segregaciones) quedan fuera; no se reasignan sin una tabla de correspondencias.
with geo as (
    select g.geo_id, g.geo_type as nivel,
           case g.geo_type when 'municipio' then g.parent_geo_id when 'provincia' then g.geo_id end as provincia_id,
           case g.geo_type when 'municipio' then p.parent_geo_id when 'provincia' then g.parent_geo_id
                           when 'ccaa' then g.geo_id end as ccaa_id
    from {{ ref('dim_geography') }} g
    left join {{ ref('dim_geography') }} p on p.geo_id = g.parent_geo_id
    where g.geo_type in ('municipio', 'provincia', 'ccaa', 'pais')
),
nivel_elec as (  -- equivalencia geo_type ↔ geo_level de las tablas electorales
    select * from (values ('municipio', 'municipio'), ('provincia', 'provincia'), ('ccaa', 'ccaa'), ('pais', 'nacional')) t(nivel, geo_level)
),
turnout as (
    select t.geo_id, t.election_id as periodo, v.variable, null::varchar as categoria, v.valor
    from {{ ref('fact_turnout') }} t
    join nivel_elec n on n.geo_level = t.geo_level
    cross join lateral (values
        ('participacion', t.turnout),
        ('abstencion', 1 - t.turnout),
        ('voto_blanco', t.blank_share),
        ('voto_nulo', t.null_share),
        ('censo', t.censo::double),
        ('votantes', t.votantes::double),
        ('votos_validos', t.votos_validos::double)
    ) v(variable, valor)
),
indices as (
    select i.geo_id, i.election_id as periodo, v.variable, null::varchar as categoria, v.valor
    from {{ ref('election_indices') }} i
    cross join lateral (values
        ('enep', i.enep), ('margen', i.margen), ('competitividad', i.competitividad), ('dominio', i.dominio)
    ) v(variable, valor)
),
volatilidad as (
    select geo_id, election_id as periodo, 'volatilidad' as variable, null::varchar as categoria, volatilidad_pedersen as valor
    from {{ ref('volatility') }}
),
familias as (
    select geo_id, election_id as periodo, 'voto_familia' as variable, familia as categoria, vote_share as valor
    from {{ ref('results_by_family') }}
),
poblacion as (
    select geo_id, anyo::varchar as periodo, 'poblacion' as variable, null::varchar as categoria, poblacion::double as valor
    from {{ ref('fact_population') }} where sexo = 'T'
),
pob_wide as (
    select geo_id,
           max(poblacion) filter (where anyo = 2025) as p2025,
           max(poblacion) filter (where anyo = 2015) as p2015,
           max(poblacion) filter (where anyo = 1996) as p1996
    from {{ ref('fact_population') }} where sexo = 'T' group by geo_id
),
derivadas as (
    select w.geo_id, v.periodo, v.variable, null::varchar as categoria, v.valor
    from pob_wide w
    -- gold.geo_boundaries la construye el paso geo de Python (atlas build), no dbt
    {% if var('has_seccionado') %}left join gold.geo_boundaries b on b.geo_id = w.geo_id
    {% else %}left join (select null::varchar geo_id, null::double area_km2) b on b.geo_id = w.geo_id{% endif %}
    cross join lateral (values
        ('2025', 'densidad', w.p2025 / nullif(b.area_km2, 0)),
        ('2015-2025', 'var_poblacion', w.p2025::double / nullif(w.p2015, 0) - 1),
        ('1996-2025', 'var_poblacion', w.p2025::double / nullif(w.p1996, 0) - 1)
    ) v(periodo, variable, valor)
),
{% if var('has_adrh') %}
adrh as (
    select 'ES-MU-' || municipios__cod as geo_id, anyo::varchar as periodo,
           case filtro_tv when '482:284048' then 'renta_persona' when '260:366831' then 'pct_65'
                          when '260:17338' then 'poblacion_adrh' end as variable,
           null::varchar as categoria,
           case when filtro_tv = '260:366831' then valor / 100 else valor end as valor
    from {{ bronze('INE-ADRH', 'tabla_*') }}
    where municipios__cod is not null and secciones__cod is null and distritos__cod is null
      and filtro_tv in ('482:284048', '260:366831', '260:17338')
),
{% endif %}
todo as (
    select * from turnout
    union all select * from indices
    union all select * from volatilidad
    union all select * from familias
    union all select * from poblacion
    union all select * from derivadas
    {% if var('has_adrh') %}union all select * from adrh{% endif %}
)
select g.geo_id, g.nivel, g.provincia_id, g.ccaa_id, t.variable, t.categoria, t.periodo, t.valor
from todo t
join geo g on g.geo_id = t.geo_id
where t.valor is not null and isfinite(t.valor)
